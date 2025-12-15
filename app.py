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
st.markdown("上传卖家精灵导出的评论表格，自动分析消费者画像与痛点。")

# --- 核心处理函数 ---

def clean_text(text):
    if pd.isna(text):
        return ""
    # 去除特殊符号，保留中文和英文
    return re.sub(r'[^\w\s\u4e00-\u9fa5]', '', str(text))

def get_keywords(text_series, top_n=20):
    text_combined = " ".join(text_series.dropna().astype(str).tolist())
    # 这里可以使用自定义词典优化，这里使用基础分词
    words = jieba.lcut(text_combined)
    # 停用词过滤（示例，实际需更完善的停用词表）
    stopwords = ['的', '了', '是', '我', '在', '和', '也', '都', '就', '用', '有', '很', '买', 'the', 'and', 'to', 'a', 'of', 'it', 'is', 'in']
    filtered_words = [w for w in words if len(w) > 1 and w.lower() not in stopwords]
    return Counter(filtered_words).most_common(top_n)

def analyze_sentiment_group(df, rating_col, content_col):
    # 简单的基于评分的情感分组
    df['Sentiment'] = df[rating_col].apply(lambda x: '差评 (痛点)' if x <= 3 else '好评 (卖点)')
    return df

# --- 侧边栏：数据上传 ---
uploaded_file = st.sidebar.file_uploader("请上传评论 Excel/CSV 文件", type=['xlsx', 'csv'])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"数据加载成功！共包含 {len(df)} 条评论。")
        
        # --- 数据列映射（根据卖家精灵导出格式调整） ---
        # 假设常见列名，如果报错，用户可在界面选择
        columns = df.columns.tolist()
        st.sidebar.markdown("### 🔧 数据列映射")
        rating_col = st.sidebar.selectbox("选择评分列", columns, index=columns.index('rating') if 'rating' in columns else 0)
        content_col = st.sidebar.selectbox("选择评论内容列", columns, index=columns.index('content') if 'content' in columns else 0)
        date_col = st.sidebar.selectbox("选择时间列", columns, index=columns.index('date') if 'date' in columns else 0)
        variant_col = st.sidebar.selectbox("选择变体/SKU列 (可选)", ['无'] + columns)

        # 数据预处理
        df = analyze_sentiment_group(df, rating_col, content_col)
        df['Cleaned_Content'] = df[content_col].apply(clean_text)

        # --- 第一部分：宏观概览 (评分与趋势) ---
        st.header("1. 宏观数据概览")
        c1, c2, c3 = st.columns(3)
        avg_rating = df[rating_col].mean()
        c1.metric("平均评分", f"{avg_rating:.2f} ⭐")
        c2.metric("评论总数", len(df))
        c3.metric("差评占比 (<=3星)", f"{(len(df[df[rating_col]<=3])/len(df)*100):.1f}%")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("评分等级分布")
            fig_rating = px.bar(df[rating_col].value_counts().sort_index(), title="星级分布图", labels={'index':'星级', 'value':'数量'})
            st.plotly_chart(fig_rating, use_container_width=True)
        
        with col2:
            st.subheader("评论时间趋势")
            if date_col:
                try:
                    df[date_col] = pd.to_datetime(df[date_col])
                    time_trend = df.resample('M', on=date_col).size().reset_index(name='count')
                    fig_time = px.line(time_trend, x=date_col, y='count', title="月度评论趋势 (淡旺季判断)")
                    st.plotly_chart(fig_time, use_container_width=True)
                except:
                    st.warning("时间格式解析失败，跳过趋势分析")

        st.markdown("---")

        # --- 第二部分：消费者画像与场景分析 ---
        st.header("2. 消费者画像与使用场景 (基于高频词)")
        
        # 提取全量关键词
        all_keywords = get_keywords(df['Cleaned_Content'], top_n=50)
        
        c_1, c_2 = st.columns(2)
        with c_1:
            st.subheader("🔍 场景与人群特征 (推测)")
            st.markdown("""
            *提示：此处基于词频统计，请结合上下文解读。*
            """)
            # 这里的逻辑是寻找特定的场景词（需人工观察高频词列表）
            word_freq_df = pd.DataFrame(all_keywords, columns=['关键词', '频率'])
            fig_cloud = px.bar(word_freq_df.head(15), x='频率', y='关键词', orientation='h', title="Top 15 核心高频词")
            fig_cloud.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_cloud, use_container_width=True)

        with c_2:
            st.subheader("💡 购买动机与好评点 (4-5星)")
            pos_df = df[df[rating_col] >= 4]
            pos_keywords = get_keywords(pos_df['Cleaned_Content'], top_n=10)
            st.write("消费者最满意的点（High Frequency）：")
            for word, freq in pos_keywords:
                st.write(f"- **{word}**: 出现 {freq} 次")

        st.markdown("---")

        # --- 第三部分：差评与痛点深度挖掘 ---
        st.header("3. ⚠️ 差评与未被满足的需求 (痛点分析)")
        
        neg_df = df[df[rating_col] <= 3]
        
        if not neg_df.empty:
            col_neg1, col_neg2 = st.columns([1, 2])
            
            with col_neg1:
                st.subheader("主要差评点")
                neg_keywords = get_keywords(neg_df['Cleaned_Content'], top_n=15)
                st.table(pd.DataFrame(neg_keywords, columns=['负面关键词', '频率']))
            
            with col_neg2:
                st.subheader("差评原文摘要 (Top 5)")
                # 简单的按长度展示几条典型的长差评，通常长差评包含更多细节
                neg_df['len'] = neg_df[content_col].astype(str).str.len()
                top_neg_reviews = neg_df.sort_values(by='len', ascending=False).head(5)
                
                for index, row in top_neg_reviews.iterrows():
                    st.error(f"⭐ {row[rating_col]}星 | {row[date_col] if date_col else ''}\n\n\"{row[content_col]}\"")
        else:
            st.success("该产品没有明显的差评（3星及以下数据为空）。")

        # --- 第四部分：变体分析 (如果有) ---
        if variant_col and variant_col != '无':
            st.header("4. 变体/规格分析")
            st.markdown("查看哪种颜色/尺寸问题最多")
            variant_counts = df.groupby(variant_col)[rating_col].mean().sort_values()
            st.bar_chart(variant_counts)

    except Exception as e:
        st.error(f"文件解析出错，请确保上传了正确的 CSV/Excel 文件。错误信息: {e}")

else:
    st.info("👆 请在左侧上传文件开始分析")
