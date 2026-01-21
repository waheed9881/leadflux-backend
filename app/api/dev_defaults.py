"""Development defaults for running the API without authentication.

This repo's frontend can run without a login flow. These helpers ensure a
default organization/user/workspace exist so routes that rely on them work
consistently in local/dev environments.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.api.routes_settings import get_or_create_default_org
from app.core.orm import UserORM, UserStatus
from app.core.orm_workspaces import WorkspaceMemberORM, WorkspaceORM, WorkspaceRole


def get_or_create_default_user_and_workspace(db: Session) -> tuple[UserORM, WorkspaceORM]:
    org = get_or_create_default_org(db)

    user = db.query(UserORM).filter(UserORM.organization_id == org.id).first()
    if not user:
        user = UserORM(
            email="default@example.com",
            password_hash="",
            full_name="Default User",
            organization_id=org.id,
            status=UserStatus.active,
            is_super_admin=True,
            can_use_advanced=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Ensure existing default user can access all features in no-auth mode.
        changed = False
        if user.status != UserStatus.active:
            user.status = UserStatus.active
            changed = True
        if not getattr(user, "is_super_admin", False):
            user.is_super_admin = True
            changed = True
        if not getattr(user, "can_use_advanced", False):
            user.can_use_advanced = True
            changed = True
        if changed:
            db.add(user)
            db.commit()
            db.refresh(user)

    workspace = db.query(WorkspaceORM).filter(WorkspaceORM.organization_id == org.id).first()
    if not workspace:
        workspace = WorkspaceORM(
            name="Default Workspace",
            slug="default",
            organization_id=org.id,
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

    membership = (
        db.query(WorkspaceMemberORM)
        .filter(
            WorkspaceMemberORM.workspace_id == workspace.id,
            WorkspaceMemberORM.user_id == user.id,
        )
        .first()
    )
    if not membership:
        db.add(
            WorkspaceMemberORM(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.owner,
                accepted_at=datetime.utcnow(),
            )
        )
        db.commit()

    if user.current_workspace_id is None:
        user.current_workspace_id = workspace.id
        db.add(user)
        db.commit()
        db.refresh(user)

    return user, workspace

