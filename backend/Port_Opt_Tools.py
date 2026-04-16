#env Gurobi
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from tqdm import tqdm
import sys

#Determine the areas that are overlapping between two sets of lat/long coordinates.
#We need this to limit the number of turbines that are placed in the same area.
def GetOverlaps_Idx_Area(LatLong1, ResolutionKm1, ResolutionDegrees1, MaxNumTurbinesPerSite1,
                         LatLong2, ResolutionKm2, ResolutionDegrees2, MaxNumTurbinesPerSite2, SameTech=1, PrintName=""):
    """
    Vectorized overlap detection between two sets of site locations.
    Uses numpy broadcasting with chunking to handle large site counts efficiently.
    
    Returns the same outputs as the original:
      IdxOverlap          : (N_pairs, 2) int array of (i, j) index pairs
      AreaOverlap         : (N_pairs,) overlap area in km^2
      AreaRef1Ref2        : (N_pairs, 2) total area of site i, site j
      MaxTurbinesRef1Ref2 : (N_pairs, 2) max turbines at site i, site j
      PercentageOverlap   : (N_pairs,) fraction of site i area that overlaps
    """
    
    # Early exit for empty inputs
    if len(LatLong1) == 0 or len(LatLong2) == 0:
        return (np.empty((0, 2), dtype=int), np.empty(0),
                np.empty((0, 2)), np.empty((0, 2)), np.empty(0))

    print('Finding Overlap Site Locations for ' + PrintName)
    
    N1 = len(LatLong1)
    N2 = len(LatLong2)
    
    # --- Precompute bounding boxes for all sites in set 1 ---
    LatKmPerDeg = 111.32  # constant
    LongKmPerDeg1 = 111.320 * np.cos(LatLong1[:, 0] * np.pi / 180)
    
    ResKm1 = ResolutionKm1.astype(np.float64)
    ResDeg1 = ResolutionDegrees1.astype(np.float64)
    use_km1 = (ResKm1 != -1)
    ResDeg1_Lat  = np.where(use_km1, ResKm1 / LatKmPerDeg,    ResDeg1)
    ResDeg1_Long = np.where(use_km1, ResKm1 / LongKmPerDeg1, ResDeg1)
    
    Lat1_lo = LatLong1[:, 0] - ResDeg1_Lat / 2
    Lat1_hi = LatLong1[:, 0] + ResDeg1_Lat / 2
    Lon1_lo = LatLong1[:, 1] - ResDeg1_Long / 2
    Lon1_hi = LatLong1[:, 1] + ResDeg1_Long / 2
    Area1 = (Lat1_hi - Lat1_lo) * LatKmPerDeg * (Lon1_hi - Lon1_lo) * LongKmPerDeg1
    
    # --- Precompute bounding boxes for all sites in set 2 ---
    LongKmPerDeg2 = 111.320 * np.cos(LatLong2[:, 0] * np.pi / 180)
    
    ResKm2 = ResolutionKm2.astype(np.float64)
    ResDeg2 = ResolutionDegrees2.astype(np.float64)
    use_km2 = (ResKm2 != -1)
    ResDeg2_Lat  = np.where(use_km2, ResKm2 / LatKmPerDeg,    ResDeg2)
    ResDeg2_Long = np.where(use_km2, ResKm2 / LongKmPerDeg2, ResDeg2)
    
    Lat2_lo = LatLong2[:, 0] - ResDeg2_Lat / 2
    Lat2_hi = LatLong2[:, 0] + ResDeg2_Lat / 2
    Lon2_lo = LatLong2[:, 1] - ResDeg2_Long / 2
    Lon2_hi = LatLong2[:, 1] + ResDeg2_Long / 2
    Area2 = (Lat2_hi - Lat2_lo) * LatKmPerDeg * (Lon2_hi - Lon2_lo) * LongKmPerDeg2
    
    # --- Spatial pre-filter: for each site i in set 1, identify which sites in
    #     set 2 are close enough to possibly overlap (within 10x the resolution).
    #     This avoids broadcasting all N1 x N2 pairs and reduces memory/compute. ---
    PREFILTER_MULT = 10  # same margin as original model

    # Build per-site candidate lists using vectorized distance check
    # For each site i, candidate j's must satisfy:
    #   |lat_j - lat_i| < PREFILTER_MULT * max(ResDeg1_Lat[i], ResDeg2_Lat[j])
    #   |lon_j - lon_i| < PREFILTER_MULT * max(ResDeg1_Long[i], ResDeg2_Long[j])
    # We approximate with the max resolution across all sites for a fast filter,
    # then do exact overlap checks on the candidates.
    max_res_lat = max(ResDeg1_Lat.max(), ResDeg2_Lat.max()) * PREFILTER_MULT
    max_res_lon = max(ResDeg1_Long.max(), ResDeg2_Long.max()) * PREFILTER_MULT

    # --- Process in chunks to manage memory ---
    CHUNK_SIZE = 2000

    IdxOverlap_list = []
    AreaOverlap_list = []
    AreaRef1Ref2_list = []
    MaxTurbinesRef1Ref2_list = []
    PercentageOverlap_list = []

    n_chunks = (N1 + CHUNK_SIZE - 1) // CHUNK_SIZE

    for chunk_idx in tqdm(range(n_chunks), desc=f"  Overlap {PrintName}", disable=(n_chunks <= 1)):
        i_start = chunk_idx * CHUNK_SIZE
        i_end = min(i_start + CHUNK_SIZE, N1)

        # --- Spatial pre-filter: only keep set2 sites within bounding box of chunk ---
        chunk_lat_lo = Lat1_lo[i_start:i_end].min() - max_res_lat
        chunk_lat_hi = Lat1_hi[i_start:i_end].max() + max_res_lat
        chunk_lon_lo = Lon1_lo[i_start:i_end].min() - max_res_lon
        chunk_lon_hi = Lon1_hi[i_start:i_end].max() + max_res_lon

        candidate_mask = ((LatLong2[:, 0] >= chunk_lat_lo) & (LatLong2[:, 0] <= chunk_lat_hi) &
                          (LatLong2[:, 1] >= chunk_lon_lo) & (LatLong2[:, 1] <= chunk_lon_hi))
        candidate_j = np.where(candidate_mask)[0]

        if len(candidate_j) == 0:
            continue

        # Broadcast: chunk of set1 (chunk_n, 1) vs candidate set2 (1, n_cand)
        ov_lat_lo = np.maximum(Lat1_lo[i_start:i_end, None], Lat2_lo[candidate_j][None, :])
        ov_lat_hi = np.minimum(Lat1_hi[i_start:i_end, None], Lat2_hi[candidate_j][None, :])
        ov_lon_lo = np.maximum(Lon1_lo[i_start:i_end, None], Lon2_lo[candidate_j][None, :])
        ov_lon_hi = np.minimum(Lon1_hi[i_start:i_end, None], Lon2_hi[candidate_j][None, :])
        
        has_overlap = (ov_lat_lo <= ov_lat_hi) & (ov_lon_lo <= ov_lon_hi)

        # For SameTech, only check j > i (upper triangle)
        if SameTech == 1:
            i_indices = np.arange(i_start, i_end)[:, None]
            j_global = candidate_j[None, :]
            has_overlap = has_overlap & (j_global > i_indices)

        # Compute overlap areas using average LongKmPerDeg (very close values)
        avg_LongKmPerDeg = (LongKmPerDeg1[i_start:i_end, None] + LongKmPerDeg2[candidate_j][None, :]) / 2

        ov_area = np.where(has_overlap,
                           (ov_lat_hi - ov_lat_lo) * LatKmPerDeg * (ov_lon_hi - ov_lon_lo) * avg_LongKmPerDeg,
                           0.0)

        # Percentage of overlap relative to site 1 area
        pct = np.where(has_overlap & (Area1[i_start:i_end, None] > 0),
                       ov_area / Area1[i_start:i_end, None], 0.0)

        # Filter: overlap > 5% of site 1 area
        valid = has_overlap & (pct > 0.05)

        ii_local, jj_local = np.where(valid)
        ii_global = ii_local + i_start
        jj_global = candidate_j[jj_local]  # Map back to original set2 indices

        if len(ii_local) > 0:
            IdxOverlap_list.append(np.column_stack((ii_global, jj_global)))
            AreaOverlap_list.append(ov_area[ii_local, jj_local])
            AreaRef1Ref2_list.append(np.column_stack((Area1[ii_global], Area2[jj_global])))
            MaxTurbinesRef1Ref2_list.append(np.column_stack((
                MaxNumTurbinesPerSite1[ii_global], MaxNumTurbinesPerSite2[jj_global])))
            PercentageOverlap_list.append(pct[ii_local, jj_local])
    
    # --- Concatenate results ---
    if len(IdxOverlap_list) > 0:
        IdxOverlap = np.concatenate(IdxOverlap_list).astype(int)
        AreaOverlap = np.concatenate(AreaOverlap_list)
        AreaRef1Ref2 = np.concatenate(AreaRef1Ref2_list)
        MaxTurbinesRef1Ref2 = np.concatenate(MaxTurbinesRef1Ref2_list)
        PercentageOverlap = np.concatenate(PercentageOverlap_list)
    else:
        IdxOverlap = np.empty((0, 2), dtype=int)
        AreaOverlap = np.empty(0)
        AreaRef1Ref2 = np.empty((0, 2))
        MaxTurbinesRef1Ref2 = np.empty((0, 2))
        PercentageOverlap = np.empty(0)
    
    print(f"  {PrintName}: {len(IdxOverlap)} overlapping pairs found")
    
    return IdxOverlap, AreaOverlap, AreaRef1Ref2, MaxTurbinesRef1Ref2, PercentageOverlap
