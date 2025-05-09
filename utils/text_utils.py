import re

def extract_tag_content(text, tag):
    # 构建正则表达式模式，匹配指定标签的内容
    pattern = f"<{tag}>(.*?)</{tag}>"
    # 使用 re.findall 查找所有匹配项，re.DOTALL 允许 . 匹配换行符
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[-1]  # 返回最后一个匹配项的内容
    return ""


def extract_special_control(input_text: str):
    """从用户输入中提取特殊控制标记，返回清理后的输入和控制内容。"""
    pattern = r'<[^>]+>'  # 正则表达式：匹配 <something> 但不包括嵌套
    match = re.search(pattern, input_text)

    if not match:
        return input_text, None

    special_str = match.group(0)[1:-1].strip()  # 提取匹配的子字符串，例如 "<example>" -> "example"
    cleaned_input = re.sub(pattern, '', input_text, count=1)  # count=1 表示只替换第一个匹配

    return cleaned_input, special_str