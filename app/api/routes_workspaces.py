"""Workspaces API routes"""
import logging
import secrets
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

from app.core.db import get_db
from app.core.orm_workspaces import WorkspaceORM, WorkspaceMemberORM, WorkspaceRole
from app.core.orm import UserORM, OrganizationORM
from app.api.routes_settings import get_or_create_default_org
from app.api.routes_auth import get_current_user
from app.api.dev_defaults import get_or_create_default_user_and_workspace
from app.services.workspace_permissions import (
    require_workspace_member,
    require_role,
    can_manage_members,
    can_manage_billing
)

logger = logging.getLogger(__name__)
router = APIRouter()

_DEFAULT_CONTEXT_IDS: Optional[Dict[str, int]] = None


def _get_default_user_and_workspace(db: Session) -> tuple[UserORM, WorkspaceORM]:
    """Return cached default user/workspace for no-auth mode (minimize DB round-trips)."""
    global _DEFAULT_CONTEXT_IDS

    if _DEFAULT_CONTEXT_IDS:
        user = db.get(UserORM, _DEFAULT_CONTEXT_IDS.get("user_id"))
        workspace = db.get(WorkspaceORM, _DEFAULT_CONTEXT_IDS.get("workspace_id"))
        if user and workspace:
            return user, workspace

    user, workspace = get_or_create_default_user_and_workspace(db)
    _DEFAULT_CONTEXT_IDS = {"user_id": user.id, "workspace_id": workspace.id}
    return user, workspace


def get_optional_token(
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """Extract optional token from Authorization header"""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return None


def get_current_user_optional(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(get_optional_token),
) -> UserORM:
    """Get current user, or create default if no auth provided"""
    # For now, always use default user to avoid auth issues
    # TODO: Add proper token validation later
    user, _ = _get_default_user_and_workspace(db)
    return user


def get_current_workspace_optional(
    workspace_id: Optional[int] = Query(None),
    x_workspace_id: Optional[int] = Header(None, alias="X-Workspace-ID"),
    db: Session = Depends(get_db),
    current_user: UserORM = Depends(get_current_user_optional),
) -> WorkspaceORM:
    """Get current workspace, or create default if no auth provided"""
    # For now, always use default workspace to avoid auth issues
    # TODO: Add proper workspace selection later
    _, workspace = _get_default_user_and_workspace(db)
    return workspace


def get_current_workspace(
    workspace_id: Optional[int] = Query(None, description="Workspace ID (from query or header)"),
    x_workspace_id: Optional[int] = Header(None, alias="X-Workspace-ID", description="Workspace ID from header"),
    db: Session = Depends(get_db),
    current_user: UserORM = Depends(get_current_user_optional),
) -> WorkspaceORM:
    """Get current workspace for the authenticated user"""
    # No-auth mode: always return the default workspace.
    _, workspace = _get_default_user_and_workspace(db)
    return workspace


# Helper to get current user (placeholder - integrate with your auth system)
def get_current_user_id(db: Session = Depends(get_db)) -> int:
    """Get current user ID from session/JWT"""
    user, _ = _get_default_user_and_workspace(db)
    return user.id


class WorkspaceCreate(BaseModel):
    """Request to create a workspace"""
    name: str = Field(..., description="Workspace name")
    description: Optional[str] = None


class WorkspaceOut(BaseModel):
    """Workspace response"""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    organization_id: int
    plan_tier: Optional[str] = None
    created_at: str
    member_count: int = 0
    current_user_role: Optional[str] = None
    
    class Config:
        from_attributes = True


class WorkspaceMemberOut(BaseModel):
    """Workspace member response"""
    id: int
    user_id: Optional[int] = None
    email: Optional[str] = None  # From user or invited_email
    full_name: Optional[str] = None
    role: str
    invited_email: Optional[str] = None
    accepted_at: Optional[str] = None
    last_active_at: Optional[str] = None
    
    class Config:
        from_attributes = True


class WorkspaceInviteRequest(BaseModel):
    """Request to invite a user to workspace"""
    email: EmailStr = Field(..., description="Email to invite")
    role: WorkspaceRole = Field(default=WorkspaceRole.member, description="Role to assign")


class WorkspaceMemberUpdate(BaseModel):
    """Request to update workspace member role"""
    role: WorkspaceRole


@router.get("/workspaces", response_model=List[WorkspaceOut])
def get_workspaces(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Get all workspaces the current user belongs to"""
    memberships = db.query(WorkspaceMemberORM).filter(
        WorkspaceMemberORM.user_id == current_user_id,
        WorkspaceMemberORM.accepted_at.isnot(None)
    ).all()
    
    workspace_ids = [m.workspace_id for m in memberships]
    
    workspaces = db.query(WorkspaceORM).filter(
        WorkspaceORM.id.in_(workspace_ids)
    ).all()
    
    result = []
    for workspace in workspaces:
        # Get member count
        member_count = db.query(WorkspaceMemberORM).filter(
            WorkspaceMemberORM.workspace_id == workspace.id,
            WorkspaceMemberORM.accepted_at.isnot(None)
        ).count()
        
        # Get current user's role
        membership = db.query(WorkspaceMemberORM).filter(
            WorkspaceMemberORM.workspace_id == workspace.id,
            WorkspaceMemberORM.user_id == current_user_id
        ).first()
        
        result.append(WorkspaceOut(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            description=workspace.description,
            organization_id=workspace.organization_id,
            plan_tier=workspace.plan_tier,
            created_at=workspace.created_at.isoformat(),
            member_count=member_count,
            current_user_role=membership.role.value if membership else None,
        ))
    
    return result


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    workspace_data: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Create a new workspace (user becomes owner)"""
    org = get_or_create_default_org(db)
    
    # Generate slug from name
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', workspace_data.name.lower()).strip('-')
    
    # Ensure uniqueness
    existing = db.query(WorkspaceORM).filter(WorkspaceORM.slug == slug).first()
    if existing:
        slug = f"{slug}-{secrets.token_hex(4)}"
    
    # Create workspace
    workspace = WorkspaceORM(
        name=workspace_data.name,
        slug=slug,
        description=workspace_data.description,
        organization_id=org.id,
    )
    db.add(workspace)
    db.flush()
    
    # Add creator as owner
    member = WorkspaceMemberORM(
        workspace_id=workspace.id,
        user_id=current_user_id,
        role=WorkspaceRole.owner,
        accepted_at=datetime.utcnow(),
    )
    db.add(member)
    db.commit()
    db.refresh(workspace)
    
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        organization_id=workspace.organization_id,
        plan_tier=workspace.plan_tier,
        created_at=workspace.created_at.isoformat(),
        member_count=1,
        current_user_role=WorkspaceRole.owner.value,
    )


@router.get("/workspaces/{workspace_id}/members", response_model=List[WorkspaceMemberOut])
def get_workspace_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Get all members of a workspace"""
    # Require membership
    require_workspace_member(db, workspace_id, current_user_id)
    
    members = db.query(WorkspaceMemberORM).filter(
        WorkspaceMemberORM.workspace_id == workspace_id
    ).all()
    
    result = []
    for member in members:
        email = None
        full_name = None
        
        if member.user_id:
            user = db.query(UserORM).filter(UserORM.id == member.user_id).first()
            if user:
                email = user.email
                full_name = user.full_name
        elif member.invited_email:
            email = member.invited_email
        
        result.append(WorkspaceMemberOut(
            id=member.id,
            user_id=member.user_id,
            email=email,
            full_name=full_name,
            role=member.role.value,
            invited_email=member.invited_email,
            accepted_at=member.accepted_at.isoformat() if member.accepted_at else None,
            last_active_at=member.last_active_at.isoformat() if member.last_active_at else None,
        ))
    
    return result


@router.post("/workspaces/{workspace_id}/members/invite", status_code=status.HTTP_201_CREATED)
def invite_workspace_member(
    workspace_id: int,
    invite_data: WorkspaceInviteRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Invite a user to the workspace"""
    # Require admin or owner
    member = require_role(db, workspace_id, current_user_id, [WorkspaceRole.owner, WorkspaceRole.admin])
    
    # Check if already a member
    existing = db.query(WorkspaceMemberORM).filter(
        WorkspaceMemberORM.workspace_id == workspace_id,
        db.or_(
            WorkspaceMemberORM.user_id.in_(
                db.query(UserORM.id).filter(UserORM.email == invite_data.email)
            ),
            WorkspaceMemberORM.invited_email == invite_data.email
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member or has a pending invite")
    
    # Check if user exists
    user = db.query(UserORM).filter(UserORM.email == invite_data.email).first()
    
    # Generate invite token
    invite_token = secrets.token_urlsafe(32)
    
    if user:
        # User exists - create membership immediately
        new_member = WorkspaceMemberORM(
            workspace_id=workspace_id,
            user_id=user.id,
            role=invite_data.role,
            accepted_at=datetime.utcnow(),
            invited_by_user_id=current_user_id,
        )
    else:
        # User doesn't exist - create pending invite
        new_member = WorkspaceMemberORM(
            workspace_id=workspace_id,
            user_id=None,
            role=invite_data.role,
            invited_email=invite_data.email,
            invite_token=invite_token,
            invited_at=datetime.utcnow(),
            invited_by_user_id=current_user_id,
        )
    
    db.add(new_member)
    db.commit()
    
    # TODO: Send invite email
    logger.info(f"Invited {invite_data.email} to workspace {workspace_id}")
    
    return {
        "message": "Invite sent",
        "member_id": new_member.id,
        "invite_token": invite_token if not user else None,
    }


@router.patch("/workspaces/{workspace_id}/members/{member_id}", response_model=WorkspaceMemberOut)
def update_workspace_member(
    workspace_id: int,
    member_id: int,
    update_data: WorkspaceMemberUpdate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Update a workspace member's role"""
    # Require admin or owner
    current_member = require_role(db, workspace_id, current_user_id, [WorkspaceRole.owner, WorkspaceRole.admin])
    
    member = db.query(WorkspaceMemberORM).filter(
        WorkspaceMemberORM.id == member_id,
        WorkspaceMemberORM.workspace_id == workspace_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Prevent changing owner role (unless you're the owner)
    if member.role == WorkspaceRole.owner and current_member.role != WorkspaceRole.owner:
        raise HTTPException(status_code=403, detail="Only the owner can change the owner's role")
    
    # Prevent removing the last owner
    if member.role == WorkspaceRole.owner and update_data.role != WorkspaceRole.owner:
        owner_count = db.query(WorkspaceMemberORM).filter(
            WorkspaceMemberORM.workspace_id == workspace_id,
            WorkspaceMemberORM.role == WorkspaceRole.owner,
            WorkspaceMemberORM.accepted_at.isnot(None)
        ).count()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")
    
    member.role = update_data.role
    db.commit()
    db.refresh(member)
    
    # Build response
    email = None
    full_name = None
    if member.user_id:
        user = db.query(UserORM).filter(UserORM.id == member.user_id).first()
        if user:
            email = user.email
            full_name = user.full_name
    elif member.invited_email:
        email = member.invited_email
    
    return WorkspaceMemberOut(
        id=member.id,
        user_id=member.user_id,
        email=email,
        full_name=full_name,
        role=member.role.value,
        invited_email=member.invited_email,
        accepted_at=member.accepted_at.isoformat() if member.accepted_at else None,
        last_active_at=member.last_active_at.isoformat() if member.last_active_at else None,
    )


@router.delete("/workspaces/{workspace_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_workspace_member(
    workspace_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Remove a member from the workspace"""
    # Require admin or owner
    current_member = require_role(db, workspace_id, current_user_id, [WorkspaceRole.owner, WorkspaceRole.admin])
    
    member = db.query(WorkspaceMemberORM).filter(
        WorkspaceMemberORM.id == member_id,
        WorkspaceMemberORM.workspace_id == workspace_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Prevent removing owner (unless you're the owner removing yourself)
    if member.role == WorkspaceRole.owner and member.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Cannot remove the owner")
    
    # Prevent removing the last owner
    if member.role == WorkspaceRole.owner:
        owner_count = db.query(WorkspaceMemberORM).filter(
            WorkspaceMemberORM.workspace_id == workspace_id,
            WorkspaceMemberORM.role == WorkspaceRole.owner,
            WorkspaceMemberORM.accepted_at.isnot(None)
        ).count()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")
    
    db.delete(member)
    db.commit()
    return


@router.post("/workspaces/{workspace_id}/switch")
def switch_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """Switch active workspace (returns workspace info for frontend to store)"""
    # Verify membership
    member = require_workspace_member(db, workspace_id, current_user_id)
    
    workspace = db.query(WorkspaceORM).filter(WorkspaceORM.id == workspace_id).first()
    
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "workspace_slug": workspace.slug,
        "user_role": member.role.value,
    }
