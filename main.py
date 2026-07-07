import re
import json
import sys
import os
import asyncio
from typing import Annotated, Literal
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

# Настройка LLM через Aitunnel
llm = ChatOpenAI(
    api_key="sk-aitunnel-6nSOCdFD2jUgDD3fzNwfJtqFbtQl8BaL",  # ← ЗАМЕНИТЕ НА НОВЫЙ КЛЮЧ!
    base_url="https://api.aitunnel.ru/v1/",
    model="gemini-3.1-flash-lite",
    max_tokens=40000,
)

# Меню пиццерии
MENU = {
    "пицца маргарита": 450,
    "пицца пепперони": 550,
    "пицца 4 сыра": 600,
    "пицца гавайская": 520,
    "пицца вегетарианская": 458,
    "кола": 120,
    "сок апельсиновый": 150,
    "вода минеральная": 80,
    "чай": 100,
}

# Состояние графа
class State(TypedDict):
    messages: Annotated[list, add_messages]
    order: dict

# Системный промпт
SYSTEM_PROMPT = f"""Ты — вежливый и дружелюбный официант в пиццерии "ПиццаМастер".

МЕНЮ:
{json.dumps(MENU, ensure_ascii=False, indent=2)}

ТВОИ ОБЯЗАННОСТИ:
1. Приветствовать гостя и помогать с выбором
2. Принимать заказы
3. Отвечать на вопросы о меню, составе пиццы и времени доставки (используй инструменты MCP!)
4. Показывать текущий заказ
5. Подсчитывать итоговую стоимость
6. Оформлять заказ

ПРАВИЛА:
- Отвечай развернуто и по-дружески
- Если гость спрашивает про состав пиццы или время доставки — ОБЯЗАТЕЛЬНО используй инструменты
- Если гость просит что-то, чего нет в меню, вежливо откажи и предложи альтернативу

Пример: "Отлично! Добавляю пиццу пепперони."
"""

# Узел: общение с клиентом
def chatbot(state: State, llm_with_tools):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# Узел: обработка заказа
def order_processor(state: State):
    last_message = state["messages"][-1].content
    order = state["order"].copy()
    
    if "[ADD:" in last_message:
        matches = re.findall(r'\[Добавили:([^:]+):(\d+)\]', last_message)
        for item, quantity in matches:
            item = item.strip().lower()
            if item in MENU:
                order[item] = order.get(item, 0) + int(quantity)
    
    elif "[REMOVE:" in last_message:
        matches = re.findall(r'\[Убрали:([^:]+):(\d+)\]', last_message)
        for item, quantity in matches:
            item = item.strip().lower()
            if item in order:
                order[item] = max(0, order[item] - int(quantity))
                if order[item] == 0:
                    del order[item]
    
    elif "[SHOW_ORDER]" in last_message:
        if order:
            order_text = "\n".join([f"  • {item} x{qty}" for item, qty in order.items()])
            state["messages"].append(AIMessage(content=f"Ваш текущий заказ:\n{order_text}"))
        else:
            state["messages"].append(AIMessage(content="Ваш заказ пока пуст. Выберите блюдо из меню!"))
    
    elif "[CALCULATE]" in last_message:
        total = sum(MENU.get(item, 0) * qty for item, qty in order.items())
        state["messages"].append(AIMessage(content=f"Итого: {total} руб."))
    
    elif "[FINISH_ORDER]" in last_message:
        if order:
            total = sum(MENU.get(item, 0) * qty for item, qty in order.items())
            order_text = "\n".join([f"  • {item} x{qty} - {MENU[item] * qty} руб." for item, qty in order.items()])
            state["messages"].append(AIMessage(content=f"✅ Заказ оформлен!\n\n{order_text}\n\nИтого: {total} руб.\nСпасибо за заказ! Ожидайте доставку через 30-40 минут."))
            order.clear()
        else:
            state["messages"].append(AIMessage(content="Ваш заказ пуст, добавьте что-нибудь из меню!"))
    
    return {"order": order, "messages": state["messages"]}

# Маршрутизация
def route_after_chatbot(state: State) -> Literal["tools", "order_processor", "__end__"]:
    last_message = state["messages"][-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    if any(cmd in last_message.content for cmd in ["[ADD:", "[REMOVE:", "[SHOW_ORDER]", "[CALCULATE]", "[FINISH_ORDER]"]):
        return "order_processor"
    
    return "__end__"

# Асинхронный ввод для Windows
async def ainput(prompt: str = ""):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))

# Главная функция
async def main():
    print("=" * 60)
    print("  🍕 Пиццерия 'ПиццаМастер' (с MCP)")
    print("=" * 60)
    print("\nДоступные позиции:")
    for item, price in MENU.items():
        print(f"  • {item} - {price} руб.")
    print("\n" + "=" * 60)
    print("Подключение к MCP серверу...")

    # ИСПРАВЛЕНО: используем абсолютный путь к mcp_server.py
    mcp_server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    
    print(f"Путь к MCP серверу: {mcp_server_path}")
    print(f"Python executable: {sys.executable}")

    # Конфигурация клиента
    client = MultiServerMCPClient({
        "pizza_mcp": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [mcp_server_path],
        }
    })
    
    try:
        # Получаем инструменты
        tools = await client.get_tools()
        print(f"✅ Загружено инструментов: {len(tools)}")
        
        llm_with_tools = llm.bind_tools(tools)

        # Сборка графа
        graph_builder = StateGraph(State)
        graph_builder.add_node("chatbot", lambda state: chatbot(state, llm_with_tools))
        graph_builder.add_node("tools", ToolNode(tools))
        graph_builder.add_node("order_processor", order_processor)

        graph_builder.add_edge(START, "chatbot")
        graph_builder.add_conditional_edges("chatbot", route_after_chatbot)
        graph_builder.add_edge("tools", "chatbot")
        graph_builder.add_edge("order_processor", END)
        
        graph = graph_builder.compile()
        print("✅ Готово! Напишите 'выход' для завершения.\n")

        state = {
            "messages": [HumanMessage(content="Здравствуйте! Я хочу сделать заказ.")],
            "order": {},
        }
        
        result = await graph.ainvoke(state)
        print(f"\n🤖 Официант: {result['messages'][-1].content}")
        state = result

        while True:
            user_input = await ainput("\n🧑 Вы: ")
            user_input = user_input.strip()

            if user_input.lower() in ("выход", "quit", "exit", "q"):
                print("👋 Спасибо за визит! До свидания!")
                break

            if not user_input:
                continue

            state["messages"].append(HumanMessage(content=user_input))
            result = await graph.ainvoke(state)
            state = result

            print(f"\n🤖 Официант: {result['messages'][-1].content}")
    
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Закрываем клиент
        try:
            await client.__aexit__(None, None, None)
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())