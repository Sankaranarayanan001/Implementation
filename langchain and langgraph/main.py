from langchain_core.messages import HumanMessage

from langgraph_setup import app

if __name__ == "__main__":
    while True:
        question = input("\nAsk anything (or 'exit'): ")
        if question.lower() == "exit":
            break
        result = app.invoke({"messages": [HumanMessage(content=question)]})
        print("Answer:", result["messages"][-1].content)
