import pandas as pd
from google.colab import files

# Tải dữ liệu
url = "https://huggingface.co/datasets/PB3002/ViMedical_Disease/resolve/main/ViMedical_Disease.csv"
df = pd.read_csv(url)

# Lưu thành JSON
filename = "ViMedical_Disease.json"
df.to_json(filename, orient="records", force_ascii=False, indent=4)

# Lệnh này sẽ mở cửa sổ Download của trình duyệt để bạn lưu về máy
files.download(filename)
