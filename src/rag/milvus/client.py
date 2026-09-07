"""Milvus 客户端 — 连接管理 + Collection 操作 + 写入/检索/删除

用户隔离策略: Partition Key
  - user_id 字段标记为 is_partition_key=True
  - Milvus 自动按 user_id 值物理分区，查询时自动剪枝
  - private 文档: user_id = 实际用户ID → 仅该用户分区
  - shared 文档:  user_id = "" (空字符串) → 公共分区，全员可搜
  - 搜索时 filter 仍携带 scope + user_id 用于双重保障
"""

import json
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger("server.milvus")

# Collection 名称
COLLECTION_NAME = "knowledge_chunks"

# Milvus Schema 字段名常量
FIELD_ID = "chunk_id"
FIELD_DOC_ID = "document_id"
FIELD_CHUNK_INDEX = "chunk_index"
FIELD_CHUNK_HASH = "chunk_hash"
FIELD_SCOPE = "scope"
FIELD_USER_ID = "user_id"          # Partition Key
FIELD_TEXT = "text"
FIELD_SOURCE_NAME = "source_name"
FIELD_PAGE_START = "page_start"
FIELD_PAGE_END = "page_end"
FIELD_SECTIONS = "sections"
FIELD_EMBEDDING = "embedding"
FIELD_CREATED_AT = "created_at"

# Partition Key 最大分区数 (默认 4096，按 user_id 分区绰绰有余)
MAX_PARTITION_NUM = 4096


@dataclass
class SearchResult:
    """检索结果"""
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    source_name: str
    scope: str
    page_start: int = 0
    page_end: int = 0
    sections: list[str] | None = None
    score: float = 0.0


class MilvusClient:
    """Milvus 向量存储客户端。

    用户隔离 (Partition Key):
      - user_id 作为 Partition Key，Milvus 自动按值物理分区
      - 搜索/删除时指定 user_id，仅扫描对应分区，性能 + 安全双赢
      - shared 文档写入空分区 (user_id="")，跨用户可检索

    管理 knowledge_chunks Collection 的完整生命周期:
      - 连接 & 创建 Schema (含 Partition Key)
      - 批量插入向量 (自动路由分区)
      - 相似度检索 (分区剪枝 + scope 过滤)
      - 按 document_id + user_id 删除 (双条件校验)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        user: str = "",
        password: str = "",
        vector_dim: int = 1024,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._vector_dim = vector_dim
        self._connected = False

    # ------------------------------------------------------------------
    # 连接 & Collection 初始化
    # ------------------------------------------------------------------

    def connect(self):
        """连接 Milvus 并确保 Collection 存在"""
        from pymilvus import connections, Collection, utility

        # 构建连接参数
        conn_args = {"host": self._host, "port": str(self._port)}
        if self._user:
            conn_args["user"] = self._user
        if self._password:
            conn_args["password"] = self._password

        connections.connect(alias="default", **conn_args)
        self._connected = True
        logger.info("Milvus 已连接: %s:%s", self._host, self._port)

        # 检查 Collection 是否需要重建 (维度或 schema 变更)
        if utility.has_collection(COLLECTION_NAME):
            collection = Collection(COLLECTION_NAME)
            # 检查现有 schema 是否有 partition key
            has_partition_key = any(
                getattr(f, "is_partition_key", False)
                for f in collection.schema.fields
            )
            if not has_partition_key:
                logger.info("Schema 不含 Partition Key，重建 Collection...")
                utility.drop_collection(COLLECTION_NAME)
                collection = self._create_collection()
            else:
                collection.load()
                logger.info("Collection '%s' 已加载 (Partition Key, %d 条)",
                             COLLECTION_NAME, collection.num_entities)
            self._collection = collection
        else:
            self._collection = self._create_collection()
            logger.info("Collection '%s' 已创建 (Partition Key)", COLLECTION_NAME)

    def _create_collection(self):
        """创建 knowledge_chunks Collection — user_id 作为 Partition Key"""
        from pymilvus import Collection, CollectionSchema, FieldSchema, DataType

        fields = [
            FieldSchema(name=FIELD_ID, dtype=DataType.VARCHAR,
                        max_length=128, is_primary=True),
            FieldSchema(name=FIELD_DOC_ID, dtype=DataType.VARCHAR,
                        max_length=64),
            FieldSchema(name=FIELD_CHUNK_INDEX, dtype=DataType.INT64),
            FieldSchema(name=FIELD_CHUNK_HASH, dtype=DataType.VARCHAR,
                        max_length=64),
            FieldSchema(name=FIELD_SCOPE, dtype=DataType.VARCHAR,
                        max_length=16),
            # Partition Key: 按 user_id 物理分区
            # - private 文档: user_id = 实际用户 → 专属分区
            # - shared 文档:  user_id = "" → 公共分区
            FieldSchema(name=FIELD_USER_ID, dtype=DataType.VARCHAR,
                        max_length=64, is_partition_key=True,
                        max_partition_num=MAX_PARTITION_NUM),
            FieldSchema(name=FIELD_TEXT, dtype=DataType.VARCHAR,
                        max_length=65535),
            FieldSchema(name=FIELD_SOURCE_NAME, dtype=DataType.VARCHAR,
                        max_length=512),
            FieldSchema(name=FIELD_PAGE_START, dtype=DataType.INT64),
            FieldSchema(name=FIELD_PAGE_END, dtype=DataType.INT64),
            FieldSchema(name=FIELD_SECTIONS, dtype=DataType.VARCHAR,
                        max_length=4096),
            FieldSchema(name=FIELD_EMBEDDING, dtype=DataType.FLOAT_VECTOR,
                        dim=self._vector_dim),
            FieldSchema(name=FIELD_CREATED_AT, dtype=DataType.INT64),
        ]

        schema = CollectionSchema(fields, description="知识库 Chunk 向量存储")
        collection = Collection(COLLECTION_NAME, schema)

        # 创建向量索引 (COSINE 距离 + AUTOINDEX)
        index_params = {
            "metric_type": "COSINE",
            "index_type": "AUTOINDEX",
            "params": {},
        }
        collection.create_index(FIELD_EMBEDDING, index_params)
        collection.load()
        return collection

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def insert(self, chunks: list[dict]) -> int:
        """批量插入 Chunk 向量。Milvus 按 user_id 自动路由分区。

        Args:
            chunks: 字典列表，每个字典包含:
                - chunk_id, document_id, chunk_index, chunk_hash,
                  scope, user_id, text, source_name,
                  page_start, page_end, sections (list→json),
                  embedding (list[float]), created_at (int timestamp)

        Returns:
            实际插入数量
        """
        if not chunks:
            return 0

        # 序列化 sections 字段
        for c in chunks:
            if "sections" in c and isinstance(c["sections"], list):
                c["sections"] = json.dumps(c["sections"], ensure_ascii=False)

        # 按 Schema 顺序构建列数据
        columns = [
            [c.get(FIELD_ID, "") for c in chunks],
            [c.get(FIELD_DOC_ID, "") for c in chunks],
            [c.get(FIELD_CHUNK_INDEX, 0) for c in chunks],
            [c.get(FIELD_CHUNK_HASH, "") for c in chunks],
            [c.get(FIELD_SCOPE, "private") for c in chunks],
            [c.get(FIELD_USER_ID, "") for c in chunks],
            [c.get(FIELD_TEXT, "") for c in chunks],
            [c.get(FIELD_SOURCE_NAME, "") for c in chunks],
            [c.get(FIELD_PAGE_START, 0) for c in chunks],
            [c.get(FIELD_PAGE_END, 0) for c in chunks],
            [c.get(FIELD_SECTIONS, "[]") for c in chunks],
            [c.get(FIELD_EMBEDDING, []) for c in chunks],
            [c.get(FIELD_CREATED_AT, int(time.time())) for c in chunks],
        ]

        result = self._collection.insert(columns)
        self._collection.flush()
        count = result.insert_count
        logger.debug("Milvus 插入: %d 条", count)
        return count

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        top_k: int = 8,
        scope: str | None = None,
        user_id: str | None = None,
    ) -> list[SearchResult]:
        """向量相似度检索 + 可选过滤。

        Partition Key 剪枝:
          - 当 user_id 非空时，Milvus 自动只扫描该用户的分区
          - shared 搜索不加 user_id 条件，扫描所有分区

        Args:
            query_vector: 查询向量
            top_k: 返回数量
            scope: 范围过滤 ("private" / "shared" / None=不过滤)
            user_id: 用户过滤 (仅 scope="private" 时生效)

        Returns:
            按相似度降序排列的 SearchResult 列表
        """
        # 构建过滤表达式
        expr_parts = []
        if scope == "private" and user_id:
            expr_parts.append(f'{FIELD_SCOPE} == "private"')
            expr_parts.append(f'{FIELD_USER_ID} == "{user_id}"')
        elif scope == "shared":
            expr_parts.append(f'{FIELD_SCOPE} == "shared"')
        elif scope:
            expr_parts.append(f'{FIELD_SCOPE} == "{scope}"')

        expr = " && ".join(expr_parts) if expr_parts else None

        search_params = {"metric_type": "COSINE", "params": {}}
        results = self._collection.search(
            data=[query_vector],
            anns_field=FIELD_EMBEDDING,
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=[
                FIELD_ID, FIELD_DOC_ID, FIELD_CHUNK_INDEX,
                FIELD_TEXT, FIELD_SOURCE_NAME, FIELD_SCOPE,
                FIELD_PAGE_START, FIELD_PAGE_END, FIELD_SECTIONS,
            ],
        )

        # 解析结果
        hits: list[SearchResult] = []
        for hits_list in results:  # 每个查询向量的结果
            for hit in hits_list:
                entity = hit.entity
                sections_raw = entity.get(FIELD_SECTIONS, "[]")
                try:
                    sections = json.loads(sections_raw) if sections_raw else []
                except (json.JSONDecodeError, TypeError):
                    sections = []

                hits.append(SearchResult(
                    chunk_id=entity.get(FIELD_ID, ""),
                    document_id=entity.get(FIELD_DOC_ID, ""),
                    chunk_index=entity.get(FIELD_CHUNK_INDEX, 0),
                    text=entity.get(FIELD_TEXT, ""),
                    source_name=entity.get(FIELD_SOURCE_NAME, ""),
                    scope=entity.get(FIELD_SCOPE, "private"),
                    page_start=entity.get(FIELD_PAGE_START, 0),
                    page_end=entity.get(FIELD_PAGE_END, 0),
                    sections=sections,
                    score=hit.score,
                ))

        return hits

    # ------------------------------------------------------------------
    # 删除 — 带 user_id 校验
    # ------------------------------------------------------------------

    def delete_by_document(self, document_id: str, user_id: str = "") -> int:
        """删除指定文档的所有 Chunk。

        必须提供 user_id:
          - private 文档: 传入文档拥有者的 user_id
          - shared 文档:  传入空字符串 ""

        双重过滤 (document_id + user_id) 防止跨用户误删。
        Partition Key 自动剪枝到目标分区，提升删除效率。

        Args:
            document_id: 文档 ID
            user_id: 文档拥有者 ID (shared=""时传空串)

        Returns:
            删除的 entity 数量
        """
        # 构建删除表达式 — 双重校验
        parts = [f'{FIELD_DOC_ID} == "{document_id}"']
        if user_id:
            parts.append(f'{FIELD_USER_ID} == "{user_id}"')
        else:
            # shared 文档: 明确限定在公共分区
            parts.append(f'{FIELD_USER_ID} == ""')

        expr = " && ".join(parts)
        result = self._collection.delete(expr)
        self._collection.flush()
        count = getattr(result, "delete_count", result)
        logger.info(
            "Milvus 删除: doc_id=%s, user_id=%s, count=%d",
            document_id, user_id, count,
        )
        return count

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def entity_count(self) -> int:
        return self._collection.num_entities

    def disconnect(self):
        """断开 Milvus 连接"""
        from pymilvus import connections
        if self._connected:
            connections.disconnect("default")
            self._connected = False
