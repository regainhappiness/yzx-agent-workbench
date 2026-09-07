---
title: "Quickstart Milvus v2.6.x documentation"
source: "https://milvus.io/docs/v2.6.x/quickstart.md"
author:
  - "[[Milvus]]"
published:
created: 2026-08-03
description: "Get started with Milvus. | v2.6.x"
tags:
  - "clippings"
---
- 关于米尔弗斯
- 开始
- 概念
- 用户指南
- 数据导入
- 人工智能工具
- 管理指南
- 工具
- 集成
- 教程
- 常见问题解答
- API 参考

## 用 Milvus Lite 快速入门

向量是神经网络模型的输出数据格式，能够有效编码信息，并在知识库、语义搜索、检索增强生成（RAG）等人工智能应用中发挥关键作用。

Milvus 是一个开源矢量数据库，适用于各种规模的人工智能应用，从在 Jupyter Notebook 中运行演示聊天机器人到构建服务数十亿用户的网络规模搜索。在本指南中，我们将带你在几分钟内本地搭建 Milvus，并使用 Python 客户端库生成、存储和搜索向量。

## 安装米尔弗斯

本指南中使用了 Milvus Lite，一个可以嵌入客户端应用的 Python 库。Milvus 还支持在 [Docker](https://milvus.io/docs/install_standalone-docker.md) 和 [Kubernetes](https://milvus.io/docs/install_cluster-milvusoperator.md) 上部署以应对生产场景。 `pymilvus`

开始之前，确保你本地环境里有 Python 3.8+。安装包含 Python 客户端库和 Milvus Lite 的版本： `pymilvus`

```python
$ pip install -U pymilvus
```

## 建立向量数据库

要创建本地的 Milvus 向量数据库，只需实例化 ，指定一个文件名来存储所有数据，例如“milvus\_demo.db”。 `MilvusClient`

```python
from pymilvus import MilvusClient

client = MilvusClient("milvus_demo.db")
```

## 创建收藏

在 Milvus 中，我们需要一个集合来存储向量及其相关的元数据。你可以把它看作传统SQL数据库中的一个表。创建集合时，你可以定义模式和索引参数，以配置向量规格，如维度、索引类型和远距度量。还有复杂的概念来优化索引以实现向量搜索性能。现在，先专注于基础，尽可能使用默认。至少，你只需要设置集合的名称和向量场的维数。

```python
if client.has_collection(collection_name="demo_collection"):
    client.drop_collection(collection_name="demo_collection")
client.create_collection(
    collection_name="demo_collection",
    dimension=768,  # The vectors we will use in this demo has 768 dimensions
)
```

在上述设置中，

- 主键和矢量字段使用默认名称（“id”和“vector”）。
- 度规类型（向量距离定义）被设置为默认值（ [COSINE）。](https://milvus.io/docs/metric.md#Cosine-Similarity)
- 主键字段接受整数，不会自动递增（即不使用 [自动识别功能](https://milvus.io/docs/schema.md) ） 或者，你也可以按照这个 [指令](https://milvus.io/api-reference/pymilvus/v2.4.x/MilvusClient/Collections/create_schema.md) 正式定义集合的模式。

## 准备数据

在本指南中，我们使用向量对文本进行语义搜索。我们需要通过下载嵌入模型来生成文本向量。这可以通过使用库中的实用函数轻松实现。 `pymilvus[model]`

## 用向量表示文本

首先，安装模型库。该软件包包含了如PyTorch等必备的机器学习工具。如果你的本地环境从未安装过PyTorch，下载包可能会花一些时间。

```python
$ pip install "pymilvus[model]"
```

用默认模型生成向量嵌入。Milvus 期望数据入，组织为词典列表，每个词典代表一个数据记录，称为实体。

```python
from pymilvus import model

# If connection to https://huggingface.co/ failed, uncomment the following path
# import os
# os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# This will download a small embedding model "paraphrase-albert-small-v2" (~50MB).
embedding_fn = model.DefaultEmbeddingFunction()

# Text strings to search from.
docs = [
    "Artificial intelligence was founded as an academic discipline in 1956.",
    "Alan Turing was the first person to conduct substantial research in AI.",
    "Born in Maida Vale, London, Turing was raised in southern England.",
]

vectors = embedding_fn.encode_documents(docs)
# The output vector has 768 dimensions, matching the collection that we just created.
print("Dim:", embedding_fn.dim, vectors[0].shape)  # Dim: 768 (768,)

# Each entity has id, vector representation, raw text, and a subject label that we use
# to demo metadata filtering later.
data = [
    {"id": i, "vector": vectors[i], "text": docs[i], "subject": "history"}
    for i in range(len(vectors))
]

print("Data has", len(data), "entities, each with fields: ", data[0].keys())
print("Vector dim:", len(data[0]["vector"]))
```
```
Dim: 768 (768,)
Data has 3 entities, each with fields:  dict_keys(['id', 'vector', 'text', 'subject'])
Vector dim: 768
```

## \[另类\]使用带有随机向量的虚假表示

如果你因为网络问题无法下载模型，作为一个巡游，你可以用随机矢量表示文本，同时完成示例。请注意，搜索结果不会反映语义相似度，因为向量是假的。

```python
import random

# Text strings to search from.
docs = [
    "Artificial intelligence was founded as an academic discipline in 1956.",
    "Alan Turing was the first person to conduct substantial research in AI.",
    "Born in Maida Vale, London, Turing was raised in southern England.",
]
# Use fake representation with random vectors (768 dimension).
vectors = [[random.uniform(-1, 1) for _ in range(768)] for _ in docs]
data = [
    {"id": i, "vector": vectors[i], "text": docs[i], "subject": "history"}
    for i in range(len(vectors))
]

print("Data has", len(data), "entities, each with fields: ", data[0].keys())
print("Vector dim:", len(data[0]["vector"]))
```
```
Data has 3 entities, each with fields:  dict_keys(['id', 'vector', 'text', 'subject'])
Vector dim: 768
```

## 插入数据

让我们把数据插入到集合中：

```python
res = client.insert(collection_name="demo_collection", data=data)

print(res)
```
```
{'insert_count': 3, 'ids': [0, 1, 2], 'cost': 0}
```

## 语义搜索

现在，我们可以通过将搜索查询文本表示为向量来进行语义搜索，并在 Milvus 上进行向量相似性搜索。

### 向量搜索

Milvus同时接受一个或多个向量搜索请求。query\_vectors变量的值是一个向量列表，每个向量是一个浮点数数组。

```python
query_vectors = embedding_fn.encode_queries(["Who is Alan Turing?"])
# If you don't have the embedding function you can use a fake vector to finish the demo:
# query_vectors = [ [ random.uniform(-1, 1) for _ in range(768) ] ]

res = client.search(
    collection_name="demo_collection",  # target collection
    data=query_vectors,  # query vectors
    limit=2,  # number of returned entities
    output_fields=["text", "subject"],  # specifies fields to be returned
)

print(res)
```
```
data: ["[{'id': 2, 'distance': 0.5859944820404053, 'entity': {'text': 'Born in Maida Vale, London, Turing was raised in southern England.', 'subject': 'history'}}, {'id': 1, 'distance': 0.5118255615234375, 'entity': {'text': 'Alan Turing was the first person to conduct substantial research in AI.', 'subject': 'history'}}]"] , extra_info: {'cost': 0}
```

输出是一份结果列表，每个结果都映射到一个向量搜索查询。每个查询包含一个结果列表，每个结果包含实体主键、查询向量的距离以及指定的实体详细信息。 `output_fields`

## 带元数据过滤的向量搜索

你也可以在考虑元数据值（在Milvus中称为“标量”字段，因为标量指非向量数据）的值时进行向量搜索。这是通过一个指定特定条件的滤波表达式实现的。让我们看看如何用下面示例中的字段进行搜索和筛选。 `subject`

```python
# Insert more docs in another subject.
docs = [
    "Machine learning has been used for drug design.",
    "Computational synthesis with AI algorithms predicts molecular properties.",
    "DDR1 is involved in cancers and fibrosis.",
]
vectors = embedding_fn.encode_documents(docs)
data = [
    {"id": 3 + i, "vector": vectors[i], "text": docs[i], "subject": "biology"}
    for i in range(len(vectors))
]

client.insert(collection_name="demo_collection", data=data)

# This will exclude any text in "history" subject despite close to the query vector.
res = client.search(
    collection_name="demo_collection",
    data=embedding_fn.encode_queries(["tell me AI related information"]),
    filter="subject == 'biology'",
    limit=2,
    output_fields=["text", "subject"],
)

print(res)
```
```
data: ["[{'id': 4, 'distance': 0.27030569314956665, 'entity': {'text': 'Computational synthesis with AI algorithms predicts molecular properties.', 'subject': 'biology'}}, {'id': 3, 'distance': 0.16425910592079163, 'entity': {'text': 'Machine learning has been used for drug design.', 'subject': 'biology'}}]"] , extra_info: {'cost': 0}
```

默认情况下，标量场不被索引。如果你需要在大数据集中进行元数据过滤搜索，可以考虑使用固定模式，同时开启 [索引](https://milvus.io/docs/scalar_index.md) 以提升搜索性能。

除了向量搜索，你还可以执行其他类型的搜索：

### 查询

query（） 是一种操作，用于检索所有符合条件的实体，例如 [过滤表达式](https://milvus.io/docs/boolean.md) 或匹配某些 ID。

例如，检索所有标量域具有特定值的实体：

```python
res = client.query(
    collection_name="demo_collection",
    filter="subject == 'history'",
    output_fields=["text", "subject"],
)
```

通过主键直接检索实体：

```python
res = client.query(
    collection_name="demo_collection",
    ids=[0, 2],
    output_fields=["vector", "text", "subject"],
)
```

## 删除实体

如果你想清除数据，可以删除指定主键的实体，或者删除所有匹配特定过滤表达式的实体。

```python
# Delete entities by primary key
res = client.delete(collection_name="demo_collection", ids=[0, 2])

print(res)

# Delete entities by a filter expression
res = client.delete(
    collection_name="demo_collection",
    filter="subject == 'biology'",
)

print(res)
```
```
[0, 2]
[3, 4, 5]
```

## 加载现有数据

由于 Milvus Lite 的所有数据都存储在本地文件中，即使程序结束，你仍可以通过用现有文件创建 A 来加载所有数据到内存中。例如，这将恢复“milvus\_demo.db”文件中的集合，并继续写入数据。 `MilvusClient`

```python
from pymilvus import MilvusClient

client = MilvusClient("milvus_demo.db")
```

## 放下收藏

如果你想删除集合中的所有数据，可以删除集合

```python
# Drop collection
client.drop_collection(collection_name="demo_collection")
```

## 了解更多

Milvus Lite 非常适合开始本地 Python 程序。如果你有大规模数据或想在生产环境中使用 Milvus，可以学习如何在 [Docker](https://milvus.io/docs/install_standalone-docker.md) 和 [Kubernetes](https://milvus.io/docs/install_cluster-milvusoperator.md) 上部署 Milvus。Milvus的所有部署模式共享同一个API，所以客户端代码在切换到另一个部署模式时不需要做太多改动。只需指定部署在任何地方的 Milvus 服务器的 [URI 和令牌](https://milvus.io/api-reference/pymilvus/v2.4.x/MilvusClient/Client/MilvusClient.md) ：

```python
client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")
```

要将数据从 Milvus Lite 迁移到 Docker 或 Kubernetes 部署的 Milvus，请参考“ [从 Milvus Lite 迁移数据](https://github.com/milvus-io/milvus-lite?tab=readme-ov-file#migrating-data-from-milvus-lite) ”。

Milvus 提供 REST 和 gRPC API，客户端库涵盖 [Python](https://milvus.io/docs/install-pymilvus.md) 、 [Java](https://milvus.io/docs/install-java.md) 、 [Go](https://milvus.io/docs/install-go.md) 、C# 和 [Node.js](https://milvus.io/docs/install-node.md) 等语言。

在模式设计方面，Milvus支持灵活模式设计，可以定义字段及其数据类型，包括向量场。你也可以为每个字段定义索引类型和参数。更多信息请参见 [搜索数据模型设计](https://milvus.io/docs/schema-hands-on.md) 。

## Milvus 用于 AI 代理

如果你使用像Claude Code或Cursor这样的AI编码助手，可以安装 [Milvus Skill](https://github.com/zilliztech/milvus-skill) ，帮助你的AI工具编写正确的Milvus代码。

如需更多代理工具，包括MCP服务器和精选提示，请参见 [Milvus的AI代理](https://milvus.io/docs/v2.6.x/milvus_for_agents.md) 。