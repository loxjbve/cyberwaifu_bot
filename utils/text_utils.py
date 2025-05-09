import re

def extract_tag_content(text, tag):
    # 构建正则表达式模式，匹配指定标签的内容
    pattern = f"<{tag}>(.*?)</{tag}>"
    # 使用 re.findall 查找所有匹配项，re.DOTALL 允许 . 匹配换行符
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[-1]  # 返回最后一个匹配项的内容
    return
