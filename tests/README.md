# 测试说明

本目录包含项目的所有测试文件，已从应用代码中分离以保持代码库整洁。

## 📁 测试文件结构

```
tests/
├── README.md                      # 本文件 - 测试说明文档
├── test_api.py                   # API 接口测试
├── test_session.py                # 会话管理测试
├── benchmark.py                  # 性能基准测试
├── run_benchmark.py              # 性能测试运行器
└── benchmark_results_*.json      # 测试结果文件
```

## 🧪 测试文件说明

### `test_api.py`
API 接口测试脚本，用于验证核心 API 端点：
- `/api/plan` - 旅行计划生成
- `/api/modify` - 行程修改
- `/api/session/{id}` - 会话查询

**使用方法**：
```bash
cd tests
python test_api.py
```

### `test_session.py`
会话管理测试脚本，验证：
- 会话创建与保存
- 会话查询与加载
- 会话更新与删除
- 历史压缩功能

**使用方法**：
```bash
cd tests
python test_session.py
```

### `benchmark.py`
性能基准测试模块，提供性能测试工具函数：
- 响应时间测试
- Token 消耗分析
- 并发性能评估
- 系统负载测试

**使用方法**：
```bash
cd tests
python benchmark.py
```

### `run_benchmark.py`
完整的性能测试运行器，生成详细的性能报告：
- 单次请求性能测试
- 批量测试与统计
- 性能数据导出
- 结果可视化分析

**使用方法**：
```bash
cd tests
python run_benchmark.py
```

## ⚙️ 测试环境配置

### 前置条件
1. **后端服务运行**：确保 FastAPI 服务已启动
   ```bash
   cd app
   uvicorn api:app --host 0.0.0.0 --port 8000
   ```

2. **环境变量配置**：复制并配置 `.env` 文件
   ```bash
   cp app/.env.example app/.env
   # 编辑 app/.env 填入实际的 API 密钥
   ```

3. **依赖安装**：确保测试依赖已安装
   ```bash
   pip install -r ../requirements.txt
   ```

## 📊 性能测试指标

测试系统会监控以下性能指标：

- **响应时间**：API 总响应时间
- **Token 消耗**：输入/输出 Token 统计
- **成本估算**：基于 Token 消耗的成本计算
- **并发性能**：多请求并发处理能力
- **错误率**：失败请求的统计分析

## 🔧 测试脚本配置

### 修改测试参数

在各测试脚本的开头部分，你可以调整以下参数：

```python
# 测试服务器地址
BASE_URL = "http://localhost:8000"

# 测试数据
TEST_CITY = "北京"
TEST_DAYS = 3

# 性能测试配置
WARMUP_REQUESTS = 3      # 预热请求数
TEST_REQUESTS = 10        # 正式测试请求数
CONCURRENT_LEVELS = [1, 5, 10]  # 并发测试级别
```

## 📈 测试结果分析

### 性能测试报告

运行 `run_benchmark.py` 后会生成 JSON 格式的性能报告：

```json
{
  "test_time": "2026-04-03T10:30:00",
  "summary": {
    "total_requests": 10,
    "avg_response_time": 3.25,
    "min_response_time": 2.8,
    "max_response_time": 4.2
  },
  "token_usage": {
    "total_input_tokens": 5000,
    "total_output_tokens": 8000,
    "estimated_cost": 0.021
  }
}
```

### 测试失败处理

- 查看控制台错误日志
- 检查后端服务状态
- 验证 API 密钥配置
- 确认网络连接正常

## 🚀 持续集成建议

### GitHub Actions 配置

建议在项目中添加 GitHub Actions 工作流来自动运行测试：

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          cd tests
          python test_api.py
          python test_session.py
```

## 📝 测试最佳实践

1. **定期运行测试**：每次代码变更后都要运行相关测试
2. **性能基准**：记录性能基准数据，监控性能变化
3. **错误报告**：测试失败时提供详细的错误日志
4. **数据清理**：测试后清理临时数据和测试会话
5. **文档更新**：添加新功能时同步更新测试文档

## ⚠️ 注意事项

- **API 限制**：注意外部 API 的调用频率限制
- **成本控制**：频繁运行 LLM 测试会产生费用
- **数据安全**：测试数据不要包含真实的敏感信息
- **网络依赖**：测试需要稳定的网络连接
- **环境隔离**：建议在测试环境中运行，避免影响生产数据

## 🐛 故障排查

### 常见问题

**问题 1：连接超时**
```
ConnectionError: HTTPConnectionPool: Max retries exceeded
```
**解决**：检查后端服务是否启动，端口是否正确

**问题 2：JSON 解析错误**
```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```
**解决**：检查 API 响应格式，确认返回正确的 JSON

**问题 3：会话未找到**
```
HTTPException: 404, detail="会话不存在"
```
**解决**：确认会话 ID 正确，会话未被清理

---

*最后更新: 2026-04-03*