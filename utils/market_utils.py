import ccxt
import pandas as pd
from datetime import datetime


def get_candlestick_data(coin, timeframe='1h', limit=40, exchange_id='binance'):
    """
    获取指定币种的K线数据，交易对默认为USDT，时间转换为UTC+8时区
    参数:
        coin: 币种 (如 'btc', 'eth')
        timeframe: K线时间周期 (如 '5m' 表示5分钟，默认5m)
        limit: 获取的K线数量 (默认40)
        exchange_id: 交易所ID (默认 'binance')
    返回:
        DataFrame: 包含K线数据的表格，时间为UTC+8时区
    """
    try:
        # 初始化交易所对象
        exchange = getattr(ccxt, exchange_id)({
            'enableRateLimit': True,  # 启用请求速率限制，避免被交易所限制
        })

        # 构造交易对，如 BTC/USDT
        symbol = f"{coin.upper()}/USDT"

        # 获取K线数据
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

        # 将数据转换为DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # 将时间戳转换为UTC时间
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)

        # 转换为UTC+8时区（北京时间）
        df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Shanghai')

        # 设置时间戳为索引
        df.set_index('timestamp', inplace=True)

        return df

    except Exception as e:
        print(f"获取数据时发生错误: {e}")
        return None


def check_coin(text):
    """
    使用字典映射检查字符串是否包含特定关键字，并根据匹配的关键字列表输出不同结果
    参数:
        text: 输入的字符串
    返回:
        str: 根据匹配结果返回对应的输出
    """
    # 定义关键字组与结果的映射字典
    keyword_mapping = {
        "btc": {
            "keywords": ["btc", "比特币", "大饼", "bitcoin"],
            "result": "btc"
        },
        "eth": {
            "keywords": ["eth", "以太坊", "以太", "小垃圾", "ethereum"],
            "result": "eth"
        },
        "xrp": {
            "keywords": ["xrp", "瑞波", "ripple"],
            "result": "xrp"
        },
        "bnb": {
            "keywords": ["bnb", "币安币", "binance coin"],
            "result": "bnb"
        },
        "usdt": {
            "keywords": ["usdt", "泰达币", "tether"],
            "result": "usdt"
        },
        "ada": {
            "keywords": ["ada", "卡尔达诺", "cardano"],
            "result": "ada"
        },
        "dot": {
            "keywords": ["dot", "波卡", "polkadot"],
            "result": "dot"
        },
        "sol": {
            "keywords": ["sol", "索拉纳", "solana"],
            "result": "sol"
        },
        "link": {
            "keywords": ["link", "链link", "chainlink"],
            "result": "link"
        },
        "matic": {
            "keywords": ["matic", "多边形", "polygon"],
            "result": "matic"
        },
        "avax": {
            "keywords": ["avax", "雪崩", "avalanche"],
            "result": "avax"
        },
        "doge": {
            "keywords": ["doge", "狗狗币",'大狗','狗子', "dogecoin"],
            "result": "doge"
        },
        "shib": {
            "keywords": ["shib", "柴犬币", 'shiba','二狗'],
            "result": "shib"
        },
        "ltc": {
            "keywords": ["ltc", "莱特", "litecoin"],
            "result": "ltc"
        },
        "bch": {
            "keywords": ["bch", "比特币现金", '太子',"bitcoin cash"],
            "result": "bch"
        },
        "atom": {
            "keywords": ["atom", "宇宙",'原子', "cosmos"],
            "result": "atom"
        },
        "xlm": {
            "keywords": ["xlm", "恒星币", "stellar"],
            "result": "xlm"
        },
        "vet": {
            "keywords": ["vet", "唯链", "vechain"],
            "result": "vet"
        },
        "trx": {
            "keywords": ["trx", "波场", "tron"],
            "result": "trx"
        },
        "eos": {
            "keywords": ["eos", "柚子", "eosio"],
            "result": "eos"
        },
        "algo": {
            "keywords": ["algo", "阿尔戈兰德", "algorand"],
            "result": "algo"
        },
        "xtz": {
            "keywords": ["xtz", "tezos", "特佐斯"],
            "result": "xtz"
        },
        "fil": {
            "keywords": ["fil", "文件币", "filecoin"],
            "result": "fil"
        },
        "theta": {
            "keywords": ["theta", "希塔", "theta network"],
            "result": "theta"
        },
        "hbar": {
            "keywords": ["hbar", "海德拉", "hedera"],
            "result": "hbar"
        },
        "ftm": {
            "keywords": ["ftm", "fantom", "幻影"],
            "result": "ftm"
        },
        "cro": {
            "keywords": ["cro", "crypto.com币", "crypto.com coin"],
            "result": "cro"
        },
        "neo": {
            "keywords": ["neo", "小蚁", "neo blockchain"],
            "result": "neo"
        },
        "iota": {
            "keywords": ["iota", "物联网币", "miota"],
            "result": "iota"
        },
        "dash": {
            "keywords": ["dash", "达世币", "digital cash"],
            "result": "dash"
        },
        "sui": {
            "keywords": ["sui"],
            "result": "sui"
        }
    }

    # 将输入字符串转为小写以忽略大小写
    text_lower = text.lower()

    # 检查每个关键字组
    for group, info in keyword_mapping.items():
        if any(keyword in text_lower for keyword in info["keywords"]):
            return info["result"]

    # 如果没有匹配到任何关键字组
    return False

# print(check_coin("大饼"))
