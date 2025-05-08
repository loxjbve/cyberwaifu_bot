import openai
import httpx
import tiktoken
from utils import db_utils as db
from utils import file_utils as file
from utils import market_utils as market
import asyncio
from utils import prompt_utils as prompt

default_api = 'gemini-2'
default_char = 'cuicuishark_public'


def build_client(key: str, url: str, model: str) -> tuple[openai.AsyncOpenAI, str]:
    """构建 OpenAI 异步客户端并返回客户端和模型名称。"""
    try:
        #print(f"使用{key},{model}获取{url}")
        http_client = httpx.AsyncClient()  # 不设置 proxies 参数
        client = openai.AsyncOpenAI(api_key=key, base_url=url, http_client=http_client)
        return client, model
    except Exception as e:
        raise ValueError(f"客户端初始化失败: {str(e)}")


async def generate_summary(conv_id):
    try:
        history = build_openai_messages(conv_id)
        history.append({"role": "user", "content": f"请你总结以上对话，输出话题名称，不要超过20字"})
        api = get_api_config(default_api)
        client, model = build_client(api[0], api[1], api[2])
        response = await client.chat.completions.create(
            model=model,
            messages=history,
            max_tokens=8000,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        raise ValueError(f"生成总结失败: {str(e)}")

async def generate_char(text):
    try:
        history = []
        history.append({"role": "user", "content": f"{text}\r\n请你根据以上描述，适当扩充或省略，输出一份json格式的角色信息"})
        api = get_api_config(default_api)
        client, model = build_client(api[0], api[1], api[2])
        response = await client.chat.completions.create(
            model=model,
            messages=history,
            max_tokens=8000,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        raise ValueError(f"生成角色失败: {str(e)}")


async def get_response_no_stream(client: openai.AsyncOpenAI, model, current_input, conv_id=0, output_type='once'):
    try:
        messages = await get_full_msg(conv_id, output_type, current_input, True)
        # print(f"完整prompts:{str(messages)}")
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=6000,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return str(RuntimeError(f"API调用失败: {str(e)}"))


async def get_response_stream(client: openai.AsyncOpenAI, model, current_input, conv_id=0, output_type='once'):
    try:
        messages = await get_full_msg(conv_id, output_type, current_input, True)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=6000,
            stream=True
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        raise RuntimeError(f"API调用失败: {str(e)}")


def get_api_config(api_name: str):
    api_list = file.load_config()['api']
    for api in api_list:
        if api['name'] == api_name:
            return api['key'], api['url'], api['model']
    raise ValueError(f"未找到名为 '{api_name}' 的API配置")


def build_openai_messages(conv_id, output_type='private'):
    dialog_history = db.dialog_content_load(conv_id, output_type)
    if not dialog_history:
        return []

    if output_type == 'group':  # 如果 type 是 'group'，限制为最近的 5 轮对话
        dialog_history = dialog_history[-10:]
    if output_type == 'private':
        dialog_history = dialog_history[-70:]

    messages = []
    for role, turn_order, content in dialog_history:
        formatted_role = role.lower()
        if formatted_role in ["user", "assistant", "system"] and content:
            messages.append({
                "role": formatted_role,
                "content": content
            })
    return messages


def calculate_token_count(text: str | None) -> int:
    try:
        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except Exception as e:
        print(f"错误: 计算token时发生错误 - {e}. 输出为字符串长度。")
        return len(str(text))


async def get_full_msg(conv_id, chat_type, current_input, split=False) -> list:
    char = None  # Initialize char to None
    if chat_type == 'private':
        char, _ = db.conversation_private_get(conv_id)
    elif chat_type == 'group':
        char, _ = db.conversation_group_config_get(conv_id)

    if char and char == default_char:
        insert_coin = market.check_coin(current_input)
        if insert_coin:
            df = await asyncio.to_thread(market.get_candlestick_data, insert_coin)
            if df is not None:
                current_input += (f"<market>\r\n这是{insert_coin}最近的走势，你需要详细输出具体的技术分析，需要提到其中的压力位(Supply)、支撑位("
                                  f"Demand)的具体点位，并分析接下来有可能的走势：\r\n{str(df)}\r\n</market>")
            else:
                print(f"警告: 未能获取 {insert_coin} 的市场数据。")
    if chat_type == 'once':
        messages = []
    else:
        messages = await asyncio.to_thread(build_openai_messages, conv_id, chat_type)
    if not split:
        messages.append({"role": "user", "content": current_input})
    else:
        prompts = prompt.split_prompts(current_input)
        messages.insert(0, {"role": "system", "content": prompts['system']})
        messages.append({"role": "user", "content": prompts['user']})
    import logging
    #logging.info(f"最终构建结果：\r\n{messages}")
    return messages


async def get_current_input_token(conv_id, chat_type, current_input, split=False):
    full_msg_content = await get_full_msg(conv_id, chat_type, current_input, split)
    return calculate_token_count(str(full_msg_content))
