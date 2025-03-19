from flask import Flask, jsonify
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
import os
import json
import base64
import traceback
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

app = Flask(__name__)

# Google Drive Folder ID where PDFs will be uploaded
DRIVE_FOLDER_ID = "182w4vy2039GqbsZ7GvGY3u3RkRukwnYl"  # Replace with your actual folder ID

def upload_to_drive(file_path):
    """Uploads a file to Google Drive."""
    try:
        print(f"📤 Uploading {file_path} to Google Drive...")

        # Authenticate with Google Drive API
        decoded_creds = base64.b64decode(os.environ["GOOGLE_CREDENTIALS"]).decode("utf-8")
        service_account_info = json.loads(decoded_creds)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, ["https://www.googleapis.com/auth/drive"])
        drive_service = build("drive", "v3", credentials=creds)

        # Upload file
        file_metadata = {
            "name": os.path.basename(file_path),
            "parents": [DRIVE_FOLDER_ID]  # Upload to shared folder
        }
        media = MediaFileUpload(file_path, mimetype="application/pdf")
        uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        print(f"✅ File uploaded successfully! File ID: {uploaded_file.get('id')}")
        return uploaded_file.get("id")

    except Exception as e:
        print(f"❌ Google Drive Upload Error: {e}")
        return None

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "✅ PDF Filler API is running"}), 200

@app.route("/fill-pdf", methods=["POST"])
def pdf_filler_tool():
    try:
        print("🔍 Decoding credentials...")
        decoded_creds = base64.b64decode(os.environ["GOOGLE_CREDENTIALS"]).decode("utf-8")
        service_account_info = json.loads(decoded_creds)

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
        client = gspread.authorize(creds)
        print("✅ Google Sheets API authentication successful.")

        # Open the Google Sheet
        sheet_name = "NOC"
        print(f"🔍 Opening Google Sheet: {sheet_name}...")
        sheet = client.open(sheet_name).sheet1

        # Read data into a Pandas DataFrame
        data = sheet.get_all_records()
        print("📄 Data retrieved:", data)
        df = pd.DataFrame(data)
        if df.empty:
            return jsonify({"error": "No data found in the Google Sheet."}), 400

        # --- Select the Most Recent Row ---
        row = df.iloc[-1]
        print("📝 Most recent row:", row.to_dict())

        # --- Map Google Sheet Columns to PDF Fields ---
        fields = {
            "Parcel ID Number": row.get("Parcel ID Number", ""),
            "Description of property": row.get("Description of property", ""),
            "Description of improvement": row.get("Description of improvement", ""),
            "Owner Name": row.get("Owner Name", ""),
            "Owner Address": row.get("Owner Address", ""),
            "Interest in property": row.get("Interest in property", ""),
        }
        
        print("📑 PDF fields mapped:", fields)

        # --- Fill the PDF Form ---
        pdf_template = "NOC_2.pdf"
        output_pdf = "filled.pdf"

        print("📖 Reading PDF template...")
        reader = PdfReader(pdf_template)
        writer = PdfWriter()

        # Copy all pages from the original PDF
        for page in reader.pages:
            writer.add_page(page)

        # Retrieve and assign AcroForm (if exists)
        acroform = reader.trailer["/Root"].get("/AcroForm")
        if acroform:
            writer._root_object[NameObject("/AcroForm")] = acroform

        # Update the fields on the first page
        writer.update_page_form_field_values(writer.pages[0], fields)
        print("✅ PDF fields updated.")

        # Write to a new PDF file
        with open(output_pdf, "wb") as output_file:
            writer.write(output_file)
        print(f"📄 PDF saved as {output_pdf}")

        # Upload the PDF to Google Drive
        file_id = upload_to_drive(output_pdf)
        if file_id:
            return jsonify({
                "message": "✅ PDF has been filled and uploaded to Google Drive",
                "file_id": file_id,
                "file_link": f"https://drive.google.com/file/d/{file_id}/view"
            }), 200
        else:
            return jsonify({"error": "❌ Failed to upload PDF to Google Drive."}), 500

    except Exception as e:
        error_message = traceback.format_exc()
        print("❌ ERROR TRACEBACK:\n", error_message)
        return jsonify({"error": str(e), "traceback": error_message}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
