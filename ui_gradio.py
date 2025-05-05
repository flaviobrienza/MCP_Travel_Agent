import gradio as gr
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.chat_message_histories import ChatMessageHistory
from mcp import StdioServerParameters
from utils import run_agent

load_dotenv()

# LLM and server
llm = ChatOpenAI(temperature=0.6)
server_params = StdioServerParameters(
    command='python',
    args=['./travel_server.py']
)

# Inizializza la memoria per la chat history
memory = ChatMessageHistory()

# Chat with agent in the UI
async def chat_with_agent(message, chat_history):
    memory.clear()
    for msg in chat_history:
        if msg["role"] == "user":
            memory.add_user_message(msg["content"])
        elif msg["role"] == "assistant":
            memory.add_ai_message(msg["content"])
    
    memory.add_user_message(message)
    
    response = await run_agent(
        prompt=message,
        server_params=server_params,
        memory=memory,
        llm=llm
    )
    
    return response

async def respond(user_message, chat_history):
    if not user_message.strip():
        return "", chat_history
    
    bot_message = await chat_with_agent(user_message, chat_history)
    
    chat_history.append({"role": "user", "content": user_message})
    chat_history.append({"role": "assistant", "content": bot_message})
    
    return "", chat_history

async def welcome():
    return "", [{"role": "assistant", "content": "Hello! I'm your holiday planner assistant. Where would you like to travel? I can help with destinations, accommodations, activities, and more!"}]

# Building UI
with gr.Blocks() as demo:
    gr.Markdown("# 🌴 Holiday Planner Companion")
    
    with gr.Row():
        with gr.Column(scale=4):
            chatbot = gr.Chatbot(
                height=600,
                show_copy_button=True,
                type="messages" 
            )
    
    with gr.Row():
        msg = gr.Textbox(
            placeholder="Where do you want to go? Ask me anything!",
            scale=4,
            container=False,
            show_label=False
        )
        submit_btn = gr.Button("Send", variant="primary", scale=1)
    

    msg.submit(respond, [msg, chatbot], [msg, chatbot])
    submit_btn.click(respond, [msg, chatbot], [msg, chatbot])
    

    demo.load(welcome, None, [msg, chatbot])

if __name__ == "__main__":
    demo.launch(share=False)