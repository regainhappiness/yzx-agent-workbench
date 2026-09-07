uvicorn src.server.main:app --reload --port 8000

# 运行测试
python -m pytest tests/test_storage.py tests/test_parsing.py tests/test_chunking.py tests/test_document_api.py -v

# 上传文件测试
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer sk-user-001" \
  -F "file=@test.txt" \
  -F "scope=private"


# 1. 启动后端
cd d:\Project\m-knowledge-assistant
uvicorn src.server.main:app --reload --host 0.0.0.0 --port 8000

# 2. 打开 webui/index.html
#    直接在浏览器中打开文件即可 (file:// 协议)
#    输入 API Base URL: http://localhost:8000/api/v1
#    输入由管理员创建并妥善保存的 API Key
#    点击 "连接"
