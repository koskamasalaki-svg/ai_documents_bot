import streamlit as st
import asyncio
import sys
import os

# Импортируем логику из main.py
from main import llm, MENU, State, chatbot, order_processor, route_after_chatbot

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

# Настройка страницы
st.set_page_config(
    page_title="🍕 ПиццаМастер",
    page_icon="🍕",
    layout="wide"
)

# Кастомный CSS для красивого дизайна
st.markdown("""
<style>
    .main {
        background-color: #f5f5f5;
    }
    .stChatMessage {
        background-color: white;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    .stButton>button {
        background-color: #ff4b4b;
        color: white;
        border-radius: 20px;
        padding: 10px 20px;
        border: none;
    }
    .stButton>button:hover {
        background-color: #ff2e2e;
    }
    h1 {
        color: #d32f2f;
        text-align: center;
    }
    .menu-item {
        background-color: white;
        padding: 10px;
        margin: 5px 0;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# Заголовок
st.markdown("<h1>🍕 Пиццерия 'ПиццаМастер'</h1>", unsafe_allow_html=True)
st.markdown("### Добро пожаловать! Я ваш виртуальный официант")

# Инициализация состояния сессии
if "messages" not in st.session_state:
    st.session_state.messages = []
if "order" not in st.session_state:
    st.session_state.order = {}

# Боковая панель с меню
with st.sidebar:
    st.markdown("## 📋 Наше меню")
    st.markdown("---")
    
    # Категории
    st.markdown("### 🍕 Пицца")
    for item, price in MENU.items():
        if "пицца" in item:
            st.markdown(f'<div class="menu-item"><b>{item.title()}</b><br>{price} руб.</div>', 
                       unsafe_allow_html=True)
    
    st.markdown("### 🥤 Напитки")
    for item, price in MENU.items():
        if "пицца" not in item:
            st.markdown(f'<div class="menu-item"><b>{item.title()}</b><br>{price} руб.</div>', 
                       unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Текущий заказ
    if st.session_state.order:
        st.markdown("### 🛒 Ваш заказ:")
        total = 0
        for item, qty in st.session_state.order.items():
            price = MENU[item] * qty
            total += price
            st.markdown(f"- {item.title()} × {qty} = {price} руб.")
        st.markdown(f"**Итого: {total} руб.**")
    else:
        st.info("Заказ пока пуст")

# Функция для создания и запуска графа
async def run_bot_async(user_message):
    mcp_server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    
    # ИСПРАВЛЕНО: создаем клиент без async with
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
        llm_with_tools = llm.bind_tools(tools)
        
        # Собираем граф
        graph_builder = StateGraph(State)
        graph_builder.add_node("chatbot", lambda state: chatbot(state, llm_with_tools))
        graph_builder.add_node("tools", ToolNode(tools))
        graph_builder.add_node("order_processor", order_processor)
        
        graph_builder.add_edge(START, "chatbot")
        graph_builder.add_conditional_edges("chatbot", route_after_chatbot)
        graph_builder.add_edge("tools", "chatbot")
        graph_builder.add_edge("order_processor", END)
        
        graph = graph_builder.compile()
        
        # Добавляем сообщение пользователя
        st.session_state.messages.append(HumanMessage(content=user_message))
        
        state = {
            "messages": st.session_state.messages.copy(),
            "order": st.session_state.order.copy(),
        }
        
        result = await graph.ainvoke(state)
        return result
        
    finally:
        # Закрываем клиент вручную
        try:
            await client.__aexit__(None, None, None)
        except:
            pass

# Отображение истории чата
for msg in st.session_state.messages:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    with st.chat_message(role):
        st.markdown(msg.content)

# Поле ввода сообщения
if prompt := st.chat_input("Напишите официанту..."):
    # Показываем сообщение пользователя
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Запускаем бота
    with st.chat_message("assistant"):
        with st.spinner("🍕 Официант думает..."):
            try:
                result = asyncio.run(run_bot_async(prompt))
                
                response_msg = result["messages"][-1]
                st.markdown(response_msg.content)
                
                # Обновляем состояние
                st.session_state.messages = result["messages"]
                st.session_state.order = result["order"]
                
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")
                import traceback
                st.code(traceback.format_exc())

# Кнопка очистки
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🗑️ Начать новый заказ"):
        st.session_state.messages = []
        st.session_state.order = {}
        st.rerun()

# Футер
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>Сделано с ❤️ для любителей пиццы</p>", 
            unsafe_allow_html=True)