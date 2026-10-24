"""Metrics and employee-search routes (US8 T091, contracts/api.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from hcm_lite.api.deps import current_user, services, today
from hcm_lite.models.domain import AuthenticatedUser
from hcm_lite.models.requests import EmployeeSearchFilters, PeriodArgs

router = APIRouter(tags=["metrics"])


def _period(period: str | None = None, start_date: str | None = None,
            end_date: str | None = None) -> PeriodArgs | None:
    if period is None and start_date is None and end_date is None:
        return None
    return PeriodArgs(period=period, start_date=start_date, end_date=end_date)


@router.get("/me")
async def me(user: AuthenticatedUser = Depends(current_user)) -> dict:
    return {"user_id": user.user_id, "username": user.username,
            "role": user.role.value, "display_name": user.display_name,
            "department": user.department}


@router.get("/me/profile")
async def my_profile(user: AuthenticatedUser = Depends(current_user),
                     svc=Depends(services)) -> dict:
    return (await svc.metrics.my_profile(user)).model_dump(mode="json")


@router.get("/metrics/headcount")
async def headcount(department: str | None = None,
                    user: AuthenticatedUser = Depends(current_user),
                    svc=Depends(services), _today=Depends(today)) -> dict:
    return (await svc.metrics.headcount(user, department, today=_today)).model_dump(mode="json")


@router.get("/metrics/attendance")
async def attendance(period: str | None = None, start_date: str | None = None,
                     end_date: str | None = None, department: str | None = None,
                     user: AuthenticatedUser = Depends(current_user),
                     svc=Depends(services), _today=Depends(today)) -> dict:
    return (await svc.metrics.attendance_summary(
        user, _period(period, start_date, end_date), department, today=_today)
    ).model_dump(mode="json")


@router.get("/metrics/late-comers")
async def late_comers(period: str | None = None, start_date: str | None = None,
                      end_date: str | None = None, department: str | None = None,
                      user: AuthenticatedUser = Depends(current_user),
                      svc=Depends(services), _today=Depends(today)) -> dict:
    return (await svc.metrics.late_comers(
        user, _period(period, start_date, end_date), department, today=_today)
    ).model_dump(mode="json")


@router.get("/metrics/leave")
async def leave_summary(period: str | None = None, start_date: str | None = None,
                        end_date: str | None = None, status: str | None = None,
                        department: str | None = None,
                        user: AuthenticatedUser = Depends(current_user),
                        svc=Depends(services), _today=Depends(today)) -> dict:
    return (await svc.metrics.leave_summary(
        user, _period(period, start_date, end_date), status, department, today=_today)
    ).model_dump(mode="json")


@router.get("/metrics/payroll")
async def payroll(period: str | None = None, department: str | None = None,
                  user: AuthenticatedUser = Depends(current_user),
                  svc=Depends(services), _today=Depends(today)) -> dict:
    return (await svc.metrics.payroll_summary(
        user, period, department, today=_today)).model_dump(mode="json")


@router.get("/employees")
async def employees(name: str | None = None, department: str | None = None,
                    job_title: str | None = None, status: str | None = Query(None),
                    user: AuthenticatedUser = Depends(current_user),
                    svc=Depends(services), _today=Depends(today)) -> dict:
    filters = EmployeeSearchFilters(name=name, department=department,
                                    job_title=job_title, status=status)
    return (await svc.metrics.search_employees(
        user, filters, today=_today)).model_dump(mode="json")
