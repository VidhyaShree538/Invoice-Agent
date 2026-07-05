import os
import logging
from pdf2image import convert_from_path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def convert_pdf_to_first_page_image(pdf_path: str, output_image_path: str) -> str:
    """
    Converts the first page of a PDF to a PNG image and saves it.
    Uses POPPLER_PATH environment variable on Windows if provided.
    """
    poppler_path = os.getenv("POPPLER_PATH")
    if poppler_path and not poppler_path.strip():
        poppler_path = None

    logger.info(f"Converting PDF {pdf_path} to image. Poppler path: {poppler_path}")

    try:
        images = convert_from_path(
            pdf_path,
            first_page=1,
            last_page=1,
            poppler_path=poppler_path
        )
        
        if not images:
            raise ValueError("No pages could be extracted from the PDF. The file might be empty or corrupt.")
        
        images[0].save(output_image_path, "PNG")
        logger.info(f"Successfully converted first page of PDF and saved to {output_image_path}")
        return output_image_path

    except FileNotFoundError as e:
        logger.error(f"Poppler not found. Error: {str(e)}")
        raise RuntimeError(
            "Poppler is required for PDF processing but could not be located. "
            "Please install Poppler and add it to your system PATH, or specify "
            "POPPLER_PATH in your .env file. E.g., POPPLER_PATH=C:\\poppler\\bin"
        ) from e
    except Exception as e:
        logger.error(f"Error during PDF to image conversion: {str(e)}")
        raise RuntimeError(f"Failed to process PDF: {str(e)}") from e
