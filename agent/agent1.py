import json
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("API_KEY")
class VinmecAgent:
    def __init__(self, data_json_path, prompt_file_path, api_key):
        # 1. Đọc dữ liệu từ file JSON
        with open(data_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 2. Đọc Prompt từ file riêng
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()

        # 3. Khởi tạo Vector Database (RAG)
        texts = [f"Bệnh: {item['disease']}. Triệu chứng: {' '.join(item['descriptions'])}" for item in data]
        self.vector_db = FAISS.from_texts(texts, OpenAIEmbeddings(openai_api_key=api_key))
        
        # 4. Cấu hình Model và Chain
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=api_key)
        self.prompt = PromptTemplate(
            template=self.prompt_template, 
            input_variables=["context", "question"]
        )
        
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_db.as_retriever(search_kwargs={"k": 1}),
            chain_type_kwargs={"prompt": self.prompt}
        )

    def handle_request(self, user_query):
        """Hàm duy nhất Backend cần gọi"""
        try:
            response = self.qa_chain.invoke(user_query)
            return response["result"]
        except Exception as e:
            return "Dạ, hệ thống đang bận, Anh/Chị vui lòng thử lại sau hoặc để lại số điện thoại để nhân viên hỗ trợ ạ."

# --- VÍ DỤ CÁCH DÙNG CHO BACKEND ---
# if __name__ == "__main__":
#     bot = VinmecAgent("medical_data.json", "medical_prompt.txt", "sk-xxx")
#     print(bot.handle_request("Tôi bị hay quên và mất định hướng"))