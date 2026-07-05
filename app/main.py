import os
import uuid
import json
import logging
from typing import List
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Load environment variables from .env before importing app modules that may use them
load_dotenv()

from app.database import engine, Base, get_db
from app.models import Invoice
from app.schemas import (
    InvoiceUploadResponse,
    InvoiceCreate,
    InvoiceResponse,
    AnalyticsResponse,
    LineItemSchema,
    ValidationFlag
)
from app.pdf_utils import convert_pdf_to_first_page_image
from app.extraction_service import extract_invoice_data
from app.validation_engine import validate_invoice

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize DB tables
Base.metadata.create_all(bind=engine)

# Create uploads directory
os.makedirs("uploads", exist_ok=True)

app = FastAPI(
    title="Invoice Processing Agent API",
    description="REST API for processing and validating invoices using local Tesseract OCR and SQLite",
    version="1.0.0"
)

# CORS middleware for local testing flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper to map database model to Pydantic-compatible dict response
def map_invoice_to_response(inv: Invoice) -> dict:
    try:
        line_items = json.loads(inv.line_items_json) if inv.line_items_json else []
    except Exception:
        line_items = []
        
    try:
        flags = json.loads(inv.flags_json) if inv.flags_json else []
    except Exception:
        flags = []

    return {
        "id": inv.id,
        "created_at": inv.created_at,
        "file_path": inv.file_path,
        "vendor_name": inv.vendor_name,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "line_items": line_items,
        "subtotal": inv.subtotal,
        "tax": inv.tax,
        "total": inv.total,
        "flags": flags,
        "status": inv.status
    }

# --- PAGE ROUTING (Serves frontend pages directly with friendly URLs) ---

@app.get("/")
async def read_index():
    return FileResponse("frontend/login.html")

@app.get("/login")
async def get_login():
    return FileResponse("frontend/login.html")

@app.get("/upload")
async def get_upload():
    return FileResponse("frontend/upload.html")

@app.get("/review")
async def get_review():
    return FileResponse("frontend/review.html")

@app.get("/history")
async def get_history():
    return FileResponse("frontend/history.html")

@app.get("/detail")
async def get_detail():
    return FileResponse("frontend/detail.html")

@app.get("/analytics")
async def get_analytics():
    return FileResponse("frontend/analytics.html")


# --- API ENDPOINTS ---

@app.post("/api/invoices/upload", response_model=InvoiceUploadResponse)
async def upload_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Accepts an invoice file (PDF or image).
    Converts PDF pages to PNG (first page) if needed.
    Runs local OCR extraction.
    Runs validation against existing database records.
    Returns the parsed fields + validation flags WITHOUT saving to the DB.
    """
    logger.info(f"Received file upload request: {file.filename}")
    
    # Check file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = [".pdf", ".png", ".jpg", ".jpeg", ".webp"]
    if file_ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format. Supported formats: {', '.join(allowed_exts)}"
        )

    # Generate a unique filename prefix to avoid name collisions
    file_id = uuid.uuid4().hex
    safe_filename = f"{file_id}_{file.filename}"
    original_file_path = os.path.join("uploads", safe_filename)

    # Save original file to disk
    try:
        with open(original_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        logger.info(f"Saved original upload to {original_file_path}")
    except Exception as e:
        logger.error(f"Failed to write file to disk: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file to disk."
        )

    # Convert PDF to Image if necessary
    processing_image_path = original_file_path
    if file_ext == ".pdf":
        png_filename = f"{file_id}_page1.png"
        processing_image_path = os.path.join("uploads", png_filename)
        try:
            logger.info("PDF file detected. Initiating Poppler conversion to first-page image...")
            convert_pdf_to_first_page_image(original_file_path, processing_image_path)
        except Exception as e:
            logger.error(f"PDF conversion failed: {str(e)}")
            # Cleanup original file if conversion failed
            if os.path.exists(original_file_path):
                os.remove(original_file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"PDF processing failed. Verify Poppler installation: {str(e)}"
            )

    # Run local invoice OCR extraction
    try:
        logger.info("Starting extraction for upload '%s' using provider '%s'.", file.filename, os.getenv("EXTRACTION_PROVIDER", "tesseract"))
        extracted_data = extract_invoice_data(processing_image_path)
        logger.info(
            "Extraction completed for upload '%s': line_items=%d subtotal=%s tax=%s total=%s",
            file.filename,
            len(extracted_data.get("line_items", [])),
            extracted_data.get("subtotal"),
            extracted_data.get("tax"),
            extracted_data.get("total"),
        )
    except Exception as e:
        logger.error(f"Invoice extraction failed: {str(e)}")
        # Cleanup files on failure
        if os.path.exists(original_file_path):
            os.remove(original_file_path)
        if file_ext == ".pdf" and os.path.exists(processing_image_path):
            os.remove(processing_image_path)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Invoice extraction failed: {str(e)}"
        )

    # Cleanup intermediate converted image if PDF to save space (keep original PDF)
    # Actually, keep the PNG so the frontend can preview it if desired, or let it go
    # Let's keep it so the frontend can preview the first page image even for PDF!
    # Wait, the prompt says: "Store the original uploaded file so it can be previewed/verified"
    # So we'll pass original_file_path to the DB.

    # Run validation against existing database records
    try:
        existing_invoices = db.query(Invoice).all()
        validation_result = validate_invoice(extracted_data, existing_invoices)
        logger.info(f"Validation completed. Status: {validation_result['status']}")
    except Exception as e:
        logger.error(f"Validation engine failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal validation engine error: {str(e)}"
        )

    # Build and return the response
    return InvoiceUploadResponse(
        vendor_name=extracted_data.get("vendor_name"),
        invoice_number=extracted_data.get("invoice_number"),
        invoice_date=extracted_data.get("invoice_date"),
        due_date=extracted_data.get("due_date"),
        line_items=[
            LineItemSchema(
                description=item.get("description", "Line Item"),
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                amount=item.get("amount")
            ) for item in extracted_data.get("line_items", [])
        ],
        subtotal=extracted_data.get("subtotal"),
        tax=extracted_data.get("tax"),
        total=extracted_data.get("total"),
        flags=[
            ValidationFlag(type=f["type"], detail=f["detail"])
            for f in validation_result["flags"]
        ],
        status=validation_result["status"],
        file_path=original_file_path.replace("\\", "/") # Normalize path separators for web compatibility
    )


@app.post("/api/invoices", response_model=InvoiceResponse)
async def save_invoice(data: InvoiceCreate, db: Session = Depends(get_db)):
    """
    Accepts final user-reviewed invoice data.
    Re-runs validation logic.
    Persists data to SQLite database.
    """
    logger.info(f"Saving invoice: Vendor={data.vendor_name}, Inv={data.invoice_number}")

    # Re-run validation against existing records
    try:
        existing_invoices = db.query(Invoice).all()
        # Convert Pydantic request structure to standard dictionary for validation
        data_dict = data.model_dump()
        validation_result = validate_invoice(data_dict, existing_invoices)
    except Exception as e:
        logger.error(f"Validation failed during save: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed during save: {str(e)}"
        )

    # Persist database record
    try:
        new_invoice = Invoice(
            file_path=data.file_path,
            vendor_name=data.vendor_name,
            invoice_number=data.invoice_number,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            line_items_json=json.dumps([item.model_dump() for item in data.line_items]),
            subtotal=data.subtotal,
            tax=data.tax,
            total=data.total,
            flags_json=json.dumps(validation_result["flags"]),
            status=validation_result["status"]
        )
        db.add(new_invoice)
        db.commit()
        db.refresh(new_invoice)
        logger.info(f"Successfully saved invoice to DB with ID: {new_invoice.id}")
        return map_invoice_to_response(new_invoice)
    except Exception as e:
        db.rollback()
        logger.error(f"Database write failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist invoice: {str(e)}"
        )


@app.get("/api/invoices", response_model=List[InvoiceResponse])
async def get_all_invoices(db: Session = Depends(get_db)):
    """
    Returns list of all processed invoices ordered by created date (newest first).
    """
    try:
        invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
        return [map_invoice_to_response(inv) for inv in invoices]
    except Exception as e:
        logger.error(f"Failed to fetch invoices: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve history of invoices."
        )


@app.get("/api/invoices/analytics", response_model=AnalyticsResponse)
async def get_invoice_analytics(db: Session = Depends(get_db)):
    """
    Returns aggregated spend metrics by vendor and status counts for the dashboard charts.
    """
    try:
        # Aggregated spend by vendor
        all_invoices = db.query(Invoice).all()
        
        spend_dict = {}
        approved_count = 0
        needs_review_count = 0
        
        for inv in all_invoices:
            # Vendor sum aggregation
            vendor = inv.vendor_name or "Unknown Vendor"
            # Only count total if it is a valid float
            val = inv.total or 0.0
            spend_dict[vendor] = spend_dict.get(vendor, 0.0) + val
            
            # Status count aggregation
            if inv.status == "approved":
                approved_count += 1
            else:
                needs_review_count += 1

        spend_list = [{"vendor_name": name, "total_spend": round(total, 2)} for name, total in spend_dict.items()]
        
        # Sort vendor spend by descending total spend
        spend_list.sort(key=lambda x: x["total_spend"], reverse=True)

        return {
            "spend_by_vendor": spend_list,
            "status_counts": {
                "approved": approved_count,
                "needs_review": needs_review_count
            }
        }
    except Exception as e:
        logger.error(f"Failed to compile analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics dashboard data."
        )


@app.get("/api/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice_detail(invoice_id: int, db: Session = Depends(get_db)):
    """
    Returns details of a single invoice.
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID {invoice_id} not found."
        )
    return map_invoice_to_response(inv)


# --- STATIC FILES MOUNTING ---
# Mount original upload assets to /uploads
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
# Mount frontend assets (css, js, assets) to /static
app.mount("/static", StaticFiles(directory="frontend"), name="static")
