"""LinkedIn scraping API routes"""
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

from app.core.db import get_db
from app.services.linkedin_search_service import LinkedInSearchService
from app.api.routes_workspaces import get_current_user_optional, get_current_workspace_optional
from app.core.orm import UserORM
from app.core.orm_workspaces import WorkspaceORM
from app.core.orm import LeadORM, LeadStatus
from app.api.routes_settings import get_or_create_default_org
from app.services.linkedin_playwright_scraper import LinkedInPlaywrightScraper
from app.services.linkedin_capture import get_or_create_lead_from_linkedin, normalize_name

logger = logging.getLogger(__name__)
router = APIRouter()

class LinkedInSearchRequest(BaseModel):
    """Request model for LinkedIn search"""
    query: str = Field(..., description="Search query (e.g., 'software engineer', 'marketing manager')")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of profiles to scrape")
    headless: bool = Field(True, description="Run browser in headless mode")

class LinkedInProfileInfo(BaseModel):
    """LinkedIn profile information model"""
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    company_name: Optional[str] = None
    location: Optional[str] = None
    about: Optional[str] = None
    linkedin_url: str
    experience: List[Dict[str, Any]] = []
    success: bool = True
    error: Optional[str] = None

class LinkedInSearchResponse(BaseModel):
    """Response model for LinkedIn search"""
    success: bool
    results: List[LinkedInProfileInfo]
    total_found: int
    query: str

class LinkedInScrapeRequest(BaseModel):
    """Request model for single LinkedIn profile scrape"""
    linkedin_url: str = Field(..., description="LinkedIn profile URL")
    auto_find_email: bool = Field(True, description="Automatically find email")
    skip_smtp: bool = Field(False, description="Skip SMTP verification")
    headless: bool = Field(True, description="Run browser in headless mode")

class LinkedInCaptureRequest(BaseModel):
    """Request model for LinkedIn profile capture"""
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    linkedin_url: str
    company_domain: Optional[str] = None
    auto_find_email: bool = True
    skip_smtp: bool = False
    list_id: Optional[int] = None
    tags: Optional[List[str]] = None

@router.post("/linkedin/search", response_model=LinkedInSearchResponse)
async def search_linkedin(
    request: LinkedInSearchRequest,
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
    workspace: Optional[WorkspaceORM] = Depends(get_current_workspace_optional),
):
    """
    Search LinkedIn for profiles and extract their information via Google X-Ray search
    """
    try:
        logger.info(f"Starting LinkedIn search: {request.query}")
        
        # Initialize search service
        search_service = LinkedInSearchService(headless=request.headless)
        
        # Perform search and scrape
        results = await search_service.search_and_scrape(
            query=request.query,
            max_results=request.max_results
        )
        
        # Convert to response models
        profile_results = []
        for res in results:
            profile_results.append(LinkedInProfileInfo(
                full_name=res.get("full_name"),
                first_name=res.get("first_name"),
                last_name=res.get("last_name"),
                headline=res.get("headline"),
                company_name=res.get("company_name"),
                location=res.get("location"),
                about=res.get("about"),
                linkedin_url=res.get("linkedin_url", ""),
                experience=res.get("experience", []),
                success=res.get("success", True),
                error=res.get("error")
            ))
            
        return LinkedInSearchResponse(
            success=True,
            results=profile_results,
            total_found=len(profile_results),
            query=request.query
        )
        
    except Exception as e:
        logger.error(f"Error during LinkedIn search: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search LinkedIn: {str(e)}"
        )

@router.post("/leads/linkedin-scrape")
async def scrape_linkedin_profile(
    request: LinkedInScrapeRequest,
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    """
    Scrape a single LinkedIn profile (used by Chrome extension)
    """
    try:
        async with LinkedInPlaywrightScraper(headless=request.headless) as scraper:
            profile_data = await scraper.scrape_profile(request.linkedin_url)
            return {
                "success": True,
                "data": profile_data
            }
    except Exception as e:
        logger.error(f"Error scraping LinkedIn profile: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/leads/linkedin-capture")
async def capture_linkedin_profile(
    request: LinkedInCaptureRequest,
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
    workspace: Optional[WorkspaceORM] = Depends(get_current_workspace_optional),
):
    """
    Capture a LinkedIn profile as a lead (used by Chrome extension)
    """
    try:
        # Get organization
        org = get_or_create_default_org(db)
        
        # Normalize name
        first_name, last_name = normalize_name(
            request.full_name, 
            request.first_name, 
            request.last_name
        )
        
        # Create or update lead
        lead = get_or_create_lead_from_linkedin(
            db=db,
            organization_id=org.id,
            first_name=first_name,
            last_name=last_name,
            full_name=request.full_name,
            title=request.title or request.headline,
            headline=request.headline,
            company_name=request.company_name,
            company_domain=request.company_domain,
            linkedin_url=request.linkedin_url,
            workspace_id=workspace.id if workspace else None,
            owner_user_id=current_user.id if current_user else None
        )
        
        db.commit()
        
        return {
            "success": True,
            "id": lead.id,
            "full_name": lead.name,
            "email_status": {
                "email": lead.email,
                "status": lead.status,
                "confidence": 0.9 # Placeholder
            }
        }
    except Exception as e:
        logger.error(f"Error capturing LinkedIn profile: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
