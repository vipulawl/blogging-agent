import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")

BLOG_NICHE = os.getenv("BLOG_NICHE", "")
TARGET_AUDIENCE = os.getenv("TARGET_AUDIENCE", "general readers")
BLOG_TONE = os.getenv("BLOG_TONE", "informative and engaging")
BLOG_LANGUAGE = os.getenv("BLOG_LANGUAGE", "English")

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")
GSC_SITE_URL = os.getenv("GSC_SITE_URL", "")
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
