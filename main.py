from openai import OpenAI

client = OpenAI(
    api_key="sk-aitunnel-6nSOCdFD2jUgDD3fzNwfJtqFbtQl8BaL",
    base_url="https://api.aitunnel.ru/v1/",
)

print("Привет! Я ИИ-агент. Напишите что-нибудь или 'выход' для завершения.")

while True:
    user_input = input("\nВы: ")
    
    if user_input.lower() in ['выход', 'exit', 'quit']:
        print("До свидания!")
        break
    
    try:
        chat_result = client.chat.completions.create(
            messages=[{"role": "user", "content": user_input}],
            model="gemini-3.1-flash-lite",
            max_tokens=1000,
        )
        
        response = chat_result.choices[0].message.content
        print(f"\nИИ: {response}")
        
    except Exception as e:
        print(f"\nОшибка: {e}")