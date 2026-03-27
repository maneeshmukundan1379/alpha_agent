from __future__ import annotations

import os

import gradio as gr

from logic import AGENT_NAME, run_agent_chat


# Append one user message and the model reply to the chat history.
def chat_fn(message: str, history: list) -> list:
    text = (message or '').strip()
    if not text:
        return history or []
    reply = run_agent_chat(text, history or [])
    h = list(history or [])
    h.append([text, reply])
    return h


# Build the Gradio UI used to chat with the generated agent.
def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title=AGENT_NAME,
    ) as demo:
        gr.Markdown(f'# {AGENT_NAME}')
        gr.Markdown("Multi-turn chat: earlier messages stay in context for the model.")
        chat = gr.Chatbot(height=440)
        msg = gr.Textbox(show_label=False, lines=2, placeholder="Message…")
        with gr.Row():
            send = gr.Button("Send", variant="primary")
            clear = gr.Button("Clear")
        send.click(chat_fn, [msg, chat], [chat]).then(lambda: '', outputs=[msg])
        msg.submit(chat_fn, [msg, chat], [chat]).then(lambda: '', outputs=[msg])
        clear.click(lambda: [], outputs=[chat])
    return demo


demo = build_ui()

if __name__ == "__main__":
    _port = int(os.environ.get('ALPHA_AGENT_PORT', '7860'))
    demo.launch(
        server_name="127.0.0.1",
        server_port=_port,
        inbrowser=False,
        show_error=True,
        theme=gr.themes.Soft(primary_hue="cyan", neutral_hue="slate")
    )
