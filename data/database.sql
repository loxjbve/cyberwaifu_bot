create table conversations
(
    id          INTEGER not null
        constraint conversations_pk
            primary key autoincrement,
    conv_id     ANY     not null,
    user_id     ANY     not null,
    character   ANY     not null,
    preset      ANY     not null,
    summary     ANY,
    create_at   ANY,
    update_at   ANY,
    delete_mark ANY,
    turns       integer
);

create table dialogs
(
    id                integer not null
        primary key autoincrement,
    conv_id           ANY     not null,
    role              ANY     not null,
    raw_content       ANY     not null,
    turn_order        ANY     not null,
    created_at        ANY     not null,
    processed_content ANY,
    msg_id            integer
);

create table group_dialogs
(
    group_id           integer,
    msg_user           integer,
    trigger_type       TEXT,
    msg_text           TEXT,
    msg_user_name      TEXT,
    msg_id             integer,
    raw_response       TEXT,
    processed_response TEXT,
    delete_mark        TEXT,
    group_name         TEXT,
    create_at          ANY
);

create table group_user_conversations
(
    user_id     integer,
    group_id    integer,
    user_name   TEXT,
    conv_id     integer,
    delete_mark integer,
    create_at   TEXT,
    update_at   TEXT,
    turns       INTEGER,
    group_name  ANY
);

create table group_user_dialogs
(
    conv_id           ANY,
    role              ANY,
    raw_content       ANY,
    turn_order        ANY,
    created_at        ANY,
    processed_content TEXT,
    id                INTEGER
        constraint id
            primary key
);

create table groups
(
    group_id        integer primary key,
    members_list    ANY,
    call_count      integer,
    keywords        ANY,
    active          INT,
    api             TEXT,
    char            TEXT,
    preset          TEXT,
    input_token     integer,
    group_name      TEXT,
    update_time     ANY,
    rate            REAL,
    output_token    integer,
    disabled_topics TEXT,
    chat_mode       TEXT DEFAULT 'v1'
);



create table user_config
(
    uid     INT UNIQUE,
    char    TEXT,
    api     TEXT,
    preset  TEXT,
    conv_id INT,
    stream  TEXT,
    nick    TEXT,
    chat_mode TEXT DEFAULT 'v1'
);

create table user_sign
(
    user_id    integer,
    last_sign  ANY,
    sign_count integer,
    frequency  integer
);

create table users
(
    uid              integer,
    first_name       TEXT,
    last_name        TEXT,
    user_name        TEXT,
    create_at        ANY,
    conversations    integer,
    dialog_turns     integer,
    update_at        ANY,
    input_tokens     integer,
    output_tokens    integer,
    account_tier     integer,
    remain_frequency integer,
    balance          REAL
);
create table dialog_summary
(
    conv_id      integer not null,
    summary_area ANY,
    content      TEXT
);



create table user_profiles
(
    user_id          integer not null,
    group_id         integer not null,
    profile_json     TEXT,
    last_updated     ANY,
    primary key (user_id, group_id)
);

-- 模拟盘交易相关表
-- 用户模拟盘账户表
create table trading_accounts
(
    user_id              integer not null,
    group_id             integer not null,
    balance              REAL default 1000.0,   -- USDT余额
    total_pnl            REAL default 0.0,      -- 总盈亏
    trading_count        integer default 0,     -- 交易次数
    winning_trades       integer default 0,     -- 盈利次数
    losing_trades        integer default 0,     -- 亏损次数
    total_profit         REAL default 0.0,      -- 总盈利额
    total_loss           REAL default 0.0,      -- 总亏损额
    loan_count           integer default 0,     -- 贷款次数
    total_loan_amount    REAL default 0.0,      -- 贷款总额
    total_repayment_amount REAL default 0.0,    -- 还款总额
    current_debt         REAL default 0.0,      -- 当前欠款额
    total_fees           REAL default 0.0,      -- 累计手续费
    frozen_margin        REAL default 0.0,      -- 冻结保证金
    created_at           TEXT,
    updated_at           TEXT,
    primary key (user_id, group_id),
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

-- 创建账户表索引
create index idx_trading_accounts_user on trading_accounts(user_id);
create index idx_trading_accounts_group on trading_accounts(group_id);

-- 交易订单表
create table trading_orders
(
    order_id         TEXT primary key,         -- 订单ID
    user_id          integer not null,         -- 用户ID
    group_id         integer not null,         -- 群组ID
    symbol           TEXT not null,            -- 交易对，如BTC/USDT
    direction        TEXT not null,            -- 方向: 'ask'(卖出) 或 'bid'(买入)
    role             TEXT not null,            -- 角色: 'taker'(市价单) 或 'maker'(限价单)
    order_type       TEXT not null,            -- 订单属性: 'open'(开仓), 'close'(平仓), 'tp'(止盈), 'sl'(止损)
    operation        TEXT not null,            -- 操作类型: 'reduction'(减仓), 'addition'(加仓)
    status           TEXT default 'pending',   -- 订单状态: 'pending'(待成交), 'executed'(已成交), 'cancelled'(已取消)
    volume           REAL not null,            -- 订单数量(USDT价值)
    price            REAL,                     -- 委托价格，null表示市价单
    tp_price         REAL,                     -- 止盈价格
    sl_price         REAL,                     -- 止损价格
    margin_locked    REAL default 0.0,         -- 冻结保证金
    fee_rate         REAL default 0.0035,      -- 手续费率 (默认3.5%)
    actual_fee       REAL default 0.0,         -- 实际手续费
    related_position_id integer,               -- 关联的仓位ID
    created_at       TEXT not null,            -- 创建时间
    executed_at      TEXT,                     -- 成交时间
    cancelled_at     TEXT,                     -- 取消时间
    expiry_time      TEXT,                     -- 过期时间
    notes            TEXT,                     -- 备注信息
    FOREIGN KEY (user_id, group_id) REFERENCES trading_accounts(user_id, group_id)
);

-- 创建索引提高查询性能
create index idx_trading_orders_user_group on trading_orders(user_id, group_id);
create index idx_trading_orders_status on trading_orders(status);
create index idx_trading_orders_type on trading_orders(order_type);
create index idx_trading_orders_symbol on trading_orders(symbol);

-- 用户仓位表
create table trading_positions
(
    id               integer not null primary key autoincrement,
    user_id          integer not null,
    group_id         integer not null,
    symbol           TEXT not null,        -- 交易对，如BTC/USDT
    side             TEXT not null,        -- 'long'(多头) 或 'short'(空头)
    size             REAL not null,        -- 仓位大小(USDT价值)
    entry_price      REAL not null,        -- 开仓价格
    current_price    REAL,                 -- 当前价格
    pnl              REAL default 0.0,     -- 未实现盈亏
    liquidation_price REAL,                -- 强平价格
    tp_price         REAL,                 -- 止盈价格
    sl_price         REAL,                 -- 止损价格
    created_at       TEXT not null,
    updated_at       TEXT,
    FOREIGN KEY (user_id, group_id) REFERENCES trading_accounts(user_id, group_id)
);

-- 创建仓位表索引
create index idx_trading_positions_user_group on trading_positions(user_id, group_id);
create index idx_trading_positions_symbol on trading_positions(symbol);
create index idx_trading_positions_side on trading_positions(side);

-- 救济金记录表
create table begging_records
(
    user_id          integer not null,
    group_id         integer not null,
    last_begging     TEXT,                 -- 最后一次领取救济金时间
    begging_count    integer default 0,    -- 总领取次数
    primary key (user_id, group_id)
);

-- 交易历史记录表
create table trading_history
(
    id               integer not null primary key autoincrement,
    user_id          integer not null,
    group_id         integer not null,
    symbol           TEXT not null,
    side             TEXT not null,        -- 'long'(多头) 或 'short'(空头)
    action           TEXT not null,        -- 'open'(开仓), 'close'(平仓), 'liquidated'(强平)
    size             REAL not null,
    price            REAL not null,
    pnl              REAL default 0.0,     -- 实现盈亏(平仓时)
    created_at       TEXT not null,
    FOREIGN KEY (user_id, group_id) REFERENCES trading_accounts(user_id, group_id)
);

-- 创建交易历史表索引
create index idx_trading_history_user_group on trading_history(user_id, group_id);
create index idx_trading_history_symbol on trading_history(symbol);
create index idx_trading_history_action on trading_history(action);
create index idx_trading_history_created_at on trading_history(created_at DESC);

-- 价格缓存表(用于存储实时价格数据)
create table price_cache
(
    symbol           TEXT not null primary key,
    price            REAL not null,
    updated_at       TEXT not null
);

-- 贷款记录表
create table loans
(
    id               integer not null primary key autoincrement,
    user_id          integer not null,
    group_id         integer not null,
    principal        REAL not null,        -- 本金
    remaining_debt   REAL not null,        -- 剩余欠款(本金+利息)
    interest_rate    REAL default 0.002,   -- 每6小时利率(0.2%)
    initial_fee      REAL default 0.1,     -- 初始手续费(10%)
    loan_time        TEXT not null,        -- 贷款时间
    last_interest_time TEXT not null,      -- 最后一次计息时间
    status           TEXT default 'active', -- 'active', 'paid_off'
    created_at       TEXT not null,
    updated_at       TEXT
);

-- 还款记录表
create table loan_repayments
(
    id               integer not null primary key autoincrement,
    loan_id          integer not null,
    user_id          integer not null,
    group_id         integer not null,
    amount           REAL not null,        -- 还款金额
    repayment_time   TEXT not null,        -- 还款时间
    remaining_after  REAL not null,        -- 还款后剩余欠款
    created_at       TEXT not null,
    foreign key (loan_id) references loans(id)
);
