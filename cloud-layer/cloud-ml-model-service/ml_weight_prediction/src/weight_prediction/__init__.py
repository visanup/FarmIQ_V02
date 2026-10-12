"""FarmIQ individual-chicken weight prediction utilities."""

FEATURE_COLUMNS = [
    "area_mm2", "length_mm", "width_mm", "height_mm", "depth_mm", "confidence",
    "volume_proxy_area_height_mm3", "volume_proxy_lwh_mm3", "length_width_ratio",
    "bbox_area_px", "bbox_aspect_ratio", "mask_fill_ratio", "centroid_x_norm",
    "centroid_y_norm", "is_height_outlier",
    "age_days", "standard_weight_g", "standard_adg_g_per_day", "standard_fcr",
]

# These values originate from the vision inference for one detected chicken.
# Do not add capture time, age, breed/sex, or growth-standard values here: the
# visual-standard experiment deliberately withholds them from the estimator.
VISUAL_FEATURE_COLUMNS = [
    "area_mm2", "length_mm", "width_mm", "height_mm", "depth_mm", "confidence",
    "volume_proxy_area_height_mm3", "volume_proxy_lwh_mm3", "length_width_ratio",
    "bbox_area_px", "bbox_aspect_ratio", "mask_fill_ratio", "is_height_outlier",
]
