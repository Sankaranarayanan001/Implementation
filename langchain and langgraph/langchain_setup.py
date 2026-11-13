from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tools import tools

llm = ChatGroq(model="qwen/qwen3.6-27b")
llm_with_tools = llm.bind_tools(tools)

prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a concise assistant. When you call search_web, base your answer "
        "ONLY on the returned results — list the top titles and links in a short "
        "bullet list. Do NOT write long explanations or fill in information from "
        "your own knowledge. If a tool returns no useful results, say so in one sentence."
    )),
    MessagesPlaceholder(variable_name="messages"),
])

chain = prompt | llm_with_tools