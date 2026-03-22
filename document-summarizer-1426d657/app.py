from __future__ import annotations

"""
Gradio frontend for the generated agent (generic multi-turn chat).
"""

import os

import gradio as gr

from logic import AGENT_NAME, run_agent_chat


# Append one user message and the model reply to the chat history.
def chat_fn(message: str, history: list[dict], uploaded_files: object) -> list[dict]:
    text = (message or '').strip()
    if not text:
        return history or []
    
    # run_agent_chat expects the history *before* the current user message is added
    # and it handles the conversion of Gradio history formats internally.
    reply = run_agent_chat(text, history or [], uploaded_paths=uploaded_files)
    
    h = list(history or [])
    # Gradio Chatbot with type="messages" expects history as a list of dictionaries.
    # The new turn is appended as two separate messages.
    h.append({"role": "user", "content": text})
    h.append({"role": "assistant", "content": reply})
    return h


# Build the Gradio UI used to chat with the generated agent.
def build_ui() -> gr.Blocks:
    with gr.Blocks(title=AGENT_NAME) as demo:
        gr.Markdown(f'# {AGENT_NAME}')
        gr.Markdown("Multi-turn chat. Optional uploads apply to each send (same as the builder).")
        # Explicitly set type="messages" to align with the runtime error and the updated chat_fn.
        chat = gr.Chatbot(height=440, type="messages")
        uploads = gr.File(label="Context files (optional)", file_count="multiple", type="filepath")
        msg = gr.Textbox(show_label=False, lines=2, placeholder="Message…")
        with gr.Row():
            send = gr.Button("Send", variant="primary")
            clear = gr.Button("Clear")
        send.click(chat_fn, [msg, chat, uploads], [chat]).then(lambda: '', outputs=[msg])
        msg.submit(chat_fn, [msg, chat, uploads], [chat]).then(lambda: '', outputs=[msg])
        clear.click(lambda: [], outputs=[chat])
    return demo


demo = build_ui()

if __name__ == "__main__":
    _port = int(os.environ.get('ALPHA_AGENT_PORT', '7860'))
    demo.launch(server_name="127.0.0.1", server_port=_port, inbrowser=False, show_error=True, theme=gr.themes.Soft(primary_hue="cyan", neutral_hue="slate"))
