"""LLM 与 Embedding 客户端。

走 DashScope 的 OpenAI 兼容模式，使用 langchain-openai 官方包，
不再依赖 langchain-community 里已废弃的 ChatTongyi / DashScopeEmbeddings。
"""
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from .config import settings

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

llm = ChatOpenAI(
    model="qwen-plus",
    base_url=DASHSCOPE_BASE,
    api_key=settings.dashscope_api_key,
    streaming=True,
    temperature=0.7,
)

embeddings = OpenAIEmbeddings(
    model="text-embedding-v1",
    base_url=DASHSCOPE_BASE,
    api_key=settings.dashscope_api_key,
    # DashScope 兼容模式只接受原始字符串，不接受 token 数组；
    # 关掉长度检查，让它直接把文本作为 input 发出去。
    check_embedding_ctx_length=False,
)
