import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import jieba
from collections import Counter
import re

# 设置页面配置
st.set_page_config(page_title="竞品评论深度分析看板", layout="wide")

st.title("🛍️ 竞品评论深度分析看板")
st.markdown("上传卖家精灵导出的评论表格（Excel/CSV），自动分析消费者画像与痛点。")

# --- 核心处理函数 ---

def clean_text(text):
    """文本清洗：去除特殊符号，保留中文和英文。"""
    if pd.isna(text):
        return ""
    # 去除特殊符号，保留中文和英文，并转换为字符串
    return re.sub(r'[^\w\s\u4e00-\u9fa5]', '', str(text))

def get_keywords(text_series, top_n=20):
    """分词并统计高频关键词。"""
    text_combined = " ".join(text_series.dropna().astype(str).tolist())
    
    # 基础分词
    words = jieba.lcut(text_combined)
    
    # 停用词过滤（可根据需要添加更多产品相关停用词）
    stopwords = [
        '的', '了', '是', '我', '在', '和', '也', '都', '就', '用', '有', '很', '买', 
        '一个', '这款', '这个', '使用', '感觉', '可以', '非常', '就是', '不过', 
        '自己', '那里', '什么', '所以', '会', '它', '它家', '它能', 
        'the', 'and', 'to', 'a', 'of', 'it', 'is', 'in', 'for'
    ]
    # 过滤掉长度小于2的词和停用词
    filtered_words = [w.strip() for w in words if len(w.strip()) > 1 and w.lower() not in stopwords]
    return Counter(filtered_words).most_common(top_n)

# **【重要修复】**：增加 try-except 逻辑和强制类型转换，解决TypeError和IndentationError后的鲁棒性问题
def analyze_sentiment_group(df, rating_col):
    """根据评分列，创建数字评分列和情感分组列，并处理非数字值。"""
    
    # 强制将评分列转换为数字，遇到非数字值用 NaN 替代 (errors='coerce')
    df['Numeric_Rating'] = pd.to_numeric(df[rating_col], errors='coerce')
    
    # 填充 NaN 值，避免后续计算出错。这里将无评分的默认为中性 4 星。
    df['Numeric_Rating'] = df['Numeric_Rating'].fillna(4) 
    
    # 基于数字评分进行情感分组：<=3 为差评/痛点；>3 为好评/卖点
    df['Sentiment'] = df['Numeric_Rating'].apply(
        lambda x: '差评 (痛点)' if x <= 3 else '好评 (卖点)'
    )
    return df

# --- 侧边栏：数据上传与列映射 ---
uploaded_file = st.sidebar.file_uploader("请上传评论 Excel/CSV 文件", type=['xlsx', 'csv'])

if uploaded_file:
    try:
        # 根据文件类型读取数据
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"数据加载成功！共包含 {len(df)} 条评论。")
        
        # --- 数据列映射（根据卖家精灵导出格式调整） ---
        columns = df.columns.tolist()
        st.sidebar.markdown("### 🔧 数据列映射")
        
        # 尝试自动识别常用列名，失败则使用第一个列名
        def get_default_col(names):
            for n in names:
                for col in columns:
                    if n in col.lower():
                        return col
            return columns[0] if columns else '无'

        rating_col = st.sidebar.selectbox("选择评分列 (星级)", columns, 
                                        index=columns.index(get_default_col(['rating', 'star', 'score'])))
        content_col = st.sidebar.selectbox("选择评论内容列", columns, 
                                        index=columns.index(get_default_col(['content', 'review', 'text'])))
        date_col = st.sidebar.selectbox("选择时间列 (日期)", ['无'] + columns, 
                                        index=columns.index(get_default_col(['date', 'time', 'publish'])) + 1)
        variant_col = st.sidebar.selectbox("选择变体/SKU列 (可选)", ['无'] + columns)

        # 数据预处理
        df = analyze_sentiment_group(df, rating_col)
        df['Cleaned_Content'] = df[content_col].apply(clean_text)

        # --- 第一部分：宏观概览 (评分与趋势) ---
        st.header("1. 宏观数据概览")
        c1, c2, c3 = st.columns(3)
        avg_rating = df['Numeric_Rating'].mean()
        c1.metric("平均评分", f"{avg_rating:.2f} ⭐")
        c2.metric("评论总数", len(df))
        c3.metric("差评占比 (<=3星)", f"{(len(df[df['Numeric_Rating']<=3])/len(df)*100):.1f}%")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("评分等级分布")
            # 使用 Numeric_Rating 确保只统计数字评分
            fig_rating = px.bar(df['Numeric_Rating'].value_counts().sort_index(), 
                                title="星级分布图", labels={'index':'星级', 'value':'数量'})
            st.plotly_chart(fig_rating, use_container_width=True)
        
        with col2:
            st.subheader("评论时间趋势 (判断淡旺季)")
            if date_col != '无':
                try:
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                    time_trend = df.resample('M', on=date_col).size().reset_index(name='count')
                    fig_time = px.line(time_trend, x=date_col, y='count', title="月度评论趋势")
                    st.plotly_chart(fig_time, use_container_width=True)
                except:
                    st.warning("时间格式解析失败，跳过趋势分析")
            else:
                st.info("未选择时间列，跳过趋势分析。")

        st.markdown("---")

        # --- 第二部分：消费者画像与场景分析 ---
        st.header("2. 消费者画像、购买动机与好评点")
        
        pos_df = df[df['Sentiment'] == '好评 (卖点)']
        pos_keywords = get_keywords(pos_df['Cleaned_Content'], top_n=20)
        
        c_1, c_2 = st.columns(2)
        with c_1:
            st.subheader("💡 好评点/产品卖点 (Top 10)")
            st.markdown("这些词汇反映了**购买动机**和**产品优势**")
            pos_word_df = pd.DataFrame(pos_keywords, columns=['关键词', '频率']).head(10)
            fig_pos = px.bar(pos_word_df, x='频率', y='关键词', orientation='h', 
                             title="好评高频词", color='频率', color_continuous_scale=px.colors.sequential.Greens)
            fig_pos.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_pos, use_container_width=True)

        with c_2:
            st.subheader("人群特征与使用场景推测")
            st.markdown("""
            **消费画像推测维度：**
            * **人群特征：** (例：送礼, 学生党, 养宠家庭)
            * **使用地点：** (例：床头, 办公室, 户外)
            * **使用时刻：** (例：出差途中, 烹饪时, 学习时)
            """)
            st.dataframe(pos_word_df)

        st.markdown("---")

        # --- 第三部分：差评与痛点深度挖掘 ---
        st.header("3. ⚠️ 差评与未被满足的需求 (核心痛点)")
        
        neg_df = df[df['Sentiment'] == '差评 (痛点)']
        
        if not neg_df.empty:
            col_neg1, col_neg2 = st.columns([1, 2])
            
            with col_neg1:
                st.subheader("主要差评点/未被满足的需求 (Top 10)")
                neg_keywords = get_keywords(neg_df['Cleaned_Content'], top_n=10)
                neg_word_df = pd.DataFrame(neg_keywords, columns=['负面关键词', '频率'])
                fig_neg = px.bar(neg_word_df, x='频率', y='负面关键词', orientation='h', 
                                 title="差评高频词", color='频率', color_continuous_scale=px.colors.sequential.Reds)
                fig_neg.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_neg, use_container_width=True)
            
            with col_neg2:
                st.subheader("典型差评原文摘要 (Top 5)")
                # 筛选出最长的5条差评，通常包含最多的细节
                neg_df['len'] = neg_df[content_col].astype(str).str.len()
                top_neg_reviews = neg_df.sort_values(by='len', ascending=False).head(5)
                
                for index, row in top_neg_reviews.iterrows():
                    st.error(f"**⭐ {int(row['Numeric_Rating'])}星** | 评论：\n\n> {row[content_col]}")
        else:
            st.success("该产品没有明显的差评（3星及以下数据为空）。")

        # --- 第四部分：变体分析 (如果有) ---
        if variant_col != '无':
            st.header("4. 变体/规格分析 (查找问题变体)")
            st.markdown("查看不同颜色/尺寸/规格的平均评分差异。")
            
            # 计算各变体的平均评分，并筛选掉评论量过少的变体
            variant_stats = df.groupby(variant_col).agg(
                avg_rating=('Numeric_Rating', 'mean'),
                count=('Numeric_Rating', 'count')
            ).reset_index()
            
            min_count = st.slider("最小评论数（过滤小样本量）：", 1, int(variant_stats['count'].max()), 
                                 max(1, int(variant_stats['count'].quantile(0.1))))
            
            variant_filtered = variant_stats[variant_stats['count'] >= min_count].sort_values(by='avg_rating')

            fig_variant = px.bar(variant_filtered, 
                                 x=variant_col, 
                                 y='avg_rating', 
                                 color='avg_rating',
                                 title="各变体平均评分对比",
                                 color_continuous_scale=px.colors.sequential.Plasma,
                                 text_auto='.2f')
            st.plotly_chart(fig_variant, use_container_width=True)

    except Exception as e:
        # 捕捉所有其他可能出现的解析错误
        st.error(f"文件解析出错，请确保上传了正确的 CSV/Excel 文件。错误信息: {e}")

else:
    st.info("👆 请在左侧上传卖家精灵导出的评论文件开始分析。")
