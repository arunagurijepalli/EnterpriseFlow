"""Role-aware professional profile page used by employee and admin portal."""
from __future__ import annotations

import io
from typing import Any

import streamlit as st

from company.store import authorize_user, get_user
from company.employee_service import get_employee_id, get_employee_profile, update_my_employee_profile
from company.user_profile_service import get_user_profile_settings, save_user_profile_settings, save_user_profile_photo, delete_user_profile_photo


def render_user_profile_page(company_id: str, user_id: str, *, mode: str = "employee") -> None:
    actor = authorize_user(company_id, user_id)
    account = get_user(user_id) or {}
    employee_id = get_employee_id(company_id, user_id)
    employee_profile = get_employee_profile(employee_id, company_id) if employee_id else {}
    profile = get_user_profile_settings(company_id, user_id)
    is_admin = mode == "admin" or str(actor.get("role") or "").casefold() == "company_admin"
    title = "Administrator Profile" if is_admin else "My Employee Profile"
    subtitle = (
        "Manage your administrator identity and contact details. Company access and role are controlled by the company."
        if is_admin else
        "Your employment identity is company-managed. Update your contact information and profile photo here."
    )

    st.markdown(
        """
        <style>
        .ef-profile-hero { padding: 22px 24px; border-radius: 18px; border: 1px solid #d9e2ef;
            background: linear-gradient(115deg, #eff7ff 0%, #f6e9ff 48%, #fff0e7 100%); margin-bottom: 18px; }
        .ef-profile-name { font-size: 25px; font-weight: 800; color: #20202b; margin-bottom: 4px; }
        .ef-profile-meta { color: #53566a; font-size: 13px; line-height: 1.6; }
        .ef-profile-section { color: #20202b; font-size: 17px; font-weight: 750; margin-top: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title(title)
    st.caption(subtitle)

    full_name = str(employee_profile.get("full_name") or account.get("name") or user_id)
    email = str(employee_profile.get("email") or account.get("email") or "")
    role = str(actor.get("role") or "employee").replace("_", " ").title()
    department = str(employee_profile.get("department") or actor.get("department") or "Not assigned")
    picture = profile.get("avatar_data")

    left, right = st.columns([1, 3], vertical_alignment="center")
    with left:
        if picture:
            st.image(io.BytesIO(picture), width=132)
        else:
            initials = "".join(part[0] for part in full_name.split() if part)[:2].upper() or "EF"
            st.markdown(
                f'<div style="width:112px;height:112px;border-radius:50%;background:linear-gradient(135deg,#7b3cff,#7fb9f2);'
                f'color:white;display:flex;align-items:center;justify-content:center;font-size:34px;font-weight:800">{initials}</div>',
                unsafe_allow_html=True,
            )
    with right:
        identity_line = ("Employee ID: " + _escape(str(employee_id))) if employee_id else ("User ID: " + _escape(user_id))
        st.markdown(
            f'<div class="ef-profile-hero"><div class="ef-profile-name">{_escape(full_name)}</div>'
            f'<div class="ef-profile-meta">{_escape(email)}<br>{_escape(role)} · {_escape(department)}<br>{identity_line}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="ef-profile-section">Personal details</div>', unsafe_allow_html=True)
    st.caption("Phone and location are self-service fields. Name, email, department and role remain read-only.")
    with st.form(f"user_profile_form_{company_id}_{user_id}"):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Full name", value=full_name, disabled=True)
            phone = st.text_input("Phone number", value=str(profile.get("phone") or employee_profile.get("phone") or ""), max_chars=40)
        with col2:
            st.text_input("Work email", value=email, disabled=True)
            location = st.text_input("Office / work location", value=str(profile.get("location") or employee_profile.get("location") or ""), max_chars=120)
        st.text_input("Department", value=department, disabled=True)
        st.text_input("Role / access level", value=role, disabled=True)
        photo = st.file_uploader("Profile photo (PNG, JPG, WebP; max 2 MB)", type=["png", "jpg", "jpeg", "webp"], key=f"profile_photo_{company_id}_{user_id}")
        save = st.form_submit_button("Save profile changes", type="primary", use_container_width=True)

    if save:
        result = save_user_profile_settings(company_id, user_id, phone=phone, location=location)
        if result.get("status") != "success":
            st.error(result.get("message", "Profile details could not be saved."))
        else:
            if employee_id and employee_profile:
                mirrored = update_my_employee_profile(company_id, user_id, {"phone": phone, "location": location})
                if mirrored.get("status") not in {"success", "not_found"}:
                    st.warning(mirrored.get("message", "Employee master details were not updated."))
            if photo is not None:
                photo_result = save_user_profile_photo(
                    company_id, user_id,
                    file_name=photo.name,
                    file_data=photo.getvalue(),
                    mime_type=photo.type or "",
                )
                if photo_result.get("status") != "success":
                    st.error(photo_result.get("message", "Profile photo could not be saved."))
                else:
                    st.success("Profile details and photo saved successfully.")
                    st.rerun()
            else:
                st.success("Profile details saved successfully.")
                st.rerun()

    if picture:
        with st.expander("Profile photo settings"):
            st.caption(f"Current photo: {profile.get('avatar_filename') or 'Profile image'}")
            if st.button("Remove profile photo", key=f"remove_profile_photo_{company_id}_{user_id}"):
                result = delete_user_profile_photo(company_id, user_id)
                st.success(result.get("message", "Profile photo removed."))
                st.rerun()


def _escape(value: str) -> str:
    from html import escape
    return escape(str(value or ""))
