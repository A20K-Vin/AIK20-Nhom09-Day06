import os
import json

def process_medical_data(directory_path):
    result_json = []

    # Kiểm tra thư mục có tồn tại không
    if not os.path.exists(directory_path):
        print(f"Thư mục {directory_path} không tồn tại.")
        return

    # Duyệt qua từng file trong thư mục
    for filename in os.listdir(directory_path):
        if filename.endswith(".txt"):
            # Lấy tên bệnh bằng cách bỏ đuôi .txt
            disease_name = filename.replace(".txt", "")
            file_path = os.path.join(directory_path, filename)

            questions = []
            try:
                # Đọc nội dung file với encoding utf-8
                with open(file_path, 'r', encoding='utf-8') as file:
                    for line in file:
                        clean_line = line.strip()
                        # Chỉ lấy những dòng có nội dung
                        if clean_line:
                            questions.append(clean_line)
                
                # Tạo object cho từng loại bệnh
                disease_entry = {
                    "disease": disease_name,
                    "descriptions": questions
                }
                result_json.append(disease_entry)
                
            except Exception as e:
                print(f"Lỗi khi đọc file {filename}: {e}")

    return result_json

# --- THỰC THI ---
# Thay 'data/Question_for_dataset' bằng đường dẫn thực tế đến thư mục chứa file .txt của bạn
directory = r'C:\Users\ngoch\Downloads\AIK20-Nhom09-Day06\agent\data\Question_for_dataset' 
final_data = process_medical_data(directory)

# Xuất ra file JSON
output_file = 'medical_knowledge_base.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(final_data, f, ensure_ascii=False, indent=4)

print(f"Đã xử lý xong! Dữ liệu đã được lưu vào {output_file}")