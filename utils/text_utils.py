import re
def extract_tag_content(text, tag):
    # 构建正则表达式模式，匹配指定标签的内容
    pattern = f"<{tag}>(.*?)</{tag}>"
    # 使用 re.search 查找第一个匹配项，re.DOTALL 允许 . 匹配换行符
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)  # 返回捕获组的内容，即标签内的文本
    return ""