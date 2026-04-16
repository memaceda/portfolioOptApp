# KiteFunctions.py
# Output format compatible with portfolio optimization model.

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.interpolate import RegularGridInterpolator


def load_power_surface(power_surfaces_dir, device_id):
    d = Path(power_surfaces_dir)
    did = str(device_id)
    depth_vec = pd.read_csv(d / f"kite_{did}Depth_Vector.csv")["Depth"].values.astype(float)
    velocity_vec = pd.read_csv(d / f"kite_{did}Velocity_Vector.csv")["Velocity"].values.astype(float)
    power_mat = pd.read_csv(d / f"kite_{did}.csv", header=None).values.astype(float)
    return depth_vec, velocity_vec, power_mat


def load_cost_inputs(power_surfaces_dir, device_id):
    d = Path(power_surfaces_dir)
    vals = pd.read_csv(d / f"kite{device_id}costInp.csv", header=None).values.flatten()
    return float(vals[0]), float(vals[1]), float(vals[2])


def load_state_hycom(state_dir, depth_m):
    state_dir = Path(state_dir)
    matches = list(state_dir.glob(f"hycom_depth_{int(depth_m)}m_*.npz"))
    if not matches:
        raise FileNotFoundError(f"No file for depth {depth_m}m in {state_dir}")
    data = np.load(matches[0], allow_pickle=True)
    return {
        'datetime': data['datetime'],
        'lat': data['lat'],
        'lon': data['lon'],
        'depth': float(data['depth']),
        'ocean_speed': data['ocean_speed']
    }


def discover_states(hycom_state_dir):
    hycom_state_dir = Path(hycom_state_dir)
    states = [d.name for d in hycom_state_dir.iterdir() if d.is_dir()]
    return sorted(states) if states else []


def build_power_interpolator(depth_vec, velocity_vec, power_mat):
    return RegularGridInterpolator(
        (depth_vec, velocity_vec), power_mat,
        method='linear', bounds_error=False, fill_value=0.0
    )


def calc_power_timeseries(ocean_speed, depth_vec, velocity_vec, power_mat, operating_depth):
    n_times, n_lats, n_lons = ocean_speed.shape
    n_sites = n_lats * n_lons
    speed_flat = ocean_speed.reshape(n_times, n_sites)
    speed_flat = np.where(np.isnan(speed_flat), 0.0, speed_flat)
    interp = build_power_interpolator(depth_vec, velocity_vec, power_mat)
    power_out = np.zeros((n_times, n_sites), dtype=np.float32)
    for t in range(n_times):
        pts = np.column_stack([np.full(n_sites, operating_depth), speed_flat[t, :]])
        power_out[t, :] = interp(pts)
    return power_out


def compute_capacity_factor(power_ts, rated_power_kw):
    return np.mean(power_ts, axis=0) / rated_power_kw


def compute_lcoe(cf, capex, opex, rated_power_kw, fcr):
    annual_cost = fcr * capex + opex
    annual_energy_mwh = cf * rated_power_kw * 8760 / 1000
    with np.errstate(divide='ignore', invalid='ignore'):
        lcoe = np.where(annual_energy_mwh > 0, annual_cost / annual_energy_mwh, np.inf)
    return lcoe


def get_valid_site_mask(ocean_speed):
    n_times, n_lats, n_lons = ocean_speed.shape
    n_sites = n_lats * n_lons
    speed_flat = ocean_speed.reshape(n_times, n_sites)
    return ~np.all(np.isnan(speed_flat), axis=0)


def filter_by_median_speed(ocean_speed, min_median_speed):
    n_times, n_lats, n_lons = ocean_speed.shape
    n_sites = n_lats * n_lons
    speed_flat = ocean_speed.reshape(n_times, n_sites)
    median_speed = np.nanmedian(speed_flat, axis=0)
    return median_speed >= min_median_speed


def create_latlon_grid(lat, lon):
    lon_mesh, lat_mesh = np.meshgrid(lon, lat)
    return np.column_stack([lat_mesh.ravel(), lon_mesh.ravel()])


def process_state(state_name, state_dir, device_id, power_surfaces_dir,
                  operating_depth, fcr, min_median_speed=None):
    hycom = load_state_hycom(state_dir, operating_depth)
    depth_vec, velocity_vec, power_mat = load_power_surface(power_surfaces_dir, device_id)
    capex, opex, rated_power_kw = load_cost_inputs(power_surfaces_dir, device_id)
    
    ocean_speed = hycom['ocean_speed']
    lat, lon = hycom['lat'], hycom['lon']
    datetimes = hycom['datetime']
    
    power_ts = calc_power_timeseries(ocean_speed, depth_vec, velocity_vec, power_mat, operating_depth)
    cf = compute_capacity_factor(power_ts, rated_power_kw)
    lcoe = compute_lcoe(cf, capex, opex, rated_power_kw, fcr)
    latlon = create_latlon_grid(lat, lon)
    valid_mask = get_valid_site_mask(ocean_speed)
    
    if min_median_speed is not None:
        speed_mask = filter_by_median_speed(ocean_speed, min_median_speed)
        valid_mask = valid_mask & speed_mask
    
    return {
        'state': state_name,
        'device_id': device_id,
        'LatLong': latlon,
        'datetime': datetimes,
        'Power_kW': power_ts,
        'CapacityFactor': cf,
        'LCOE': lcoe,
        'ValidSites': valid_mask,
        'RatedPower_kW': rated_power_kw,
        'CAPEX': capex,
        'OPEX': opex,
        'Depth_m': operating_depth
    }


def save_results(results, output_path, fcr=0.1, resolution_degrees=0.08, resolution_km=8):
    """
    Save results in portfolio optimization format.
    
    Output keys match wind/wave format:
    - Energy_pu, LatLong, AnnualizedCost, RatedPower, TimeList
    - NumberOfCellsPerSite, ResolutionDegrees, ResolutionKm
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    n_sites = len(results['CapacityFactor'])
    rated_power_mw = results['RatedPower_kW'] / 1000.0
    
    # Energy_pu = capacity factor time series
    energy_pu = results['Power_kW'] / results['RatedPower_kW']
    
    # AnnualizedCost per site (M$/yr)
    annual_cost = (fcr * results['CAPEX'] + results['OPEX']) / 1e6
    annualized_cost = np.full(n_sites, annual_cost, dtype=np.float32)
    
    # NumberOfCellsPerSite = 1 for all sites
    num_cells = np.ones(n_sites, dtype=np.float64)
    
    np.savez_compressed(output_path,
        Energy_pu=energy_pu.astype(np.float16),
        LatLong=results['LatLong'].astype(np.float32),
        AnnualizedCost=annualized_cost,
        RatedPower=np.float64(rated_power_mw),
        TimeList=results['datetime'],
        NumberOfCellsPerSite=num_cells,
        ResolutionDegrees=np.float32(resolution_degrees),
        ResolutionKm=np.float32(resolution_km),
        ValidSites=results['ValidSites'],
        LCOE=results['LCOE'].astype(np.float16),
        CapacityFactor=results['CapacityFactor'].astype(np.float16),
        Depth_m=results['Depth_m'],
        CAPEX=results['CAPEX'],
        OPEX=results['OPEX']
    )


def run_all(hycom_state_dir, power_surfaces_dir, output_dir, output_template,
            device_ids, operating_depth, fcr, states=None, min_median_speed=None,
            optimize_depth=False, skip_existing=False,
            resolution_degrees=0.08, resolution_km=8):
    
    hycom_state_dir = Path(hycom_state_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if states is None:
        states = discover_states(hycom_state_dir)
    
    summaries = []
    
    for state in states:
        state_dir = hycom_state_dir / state
        if not state_dir.exists():
            print(f"Skipping {state}: folder not found")
            continue
        
        for device_id in device_ids:
            out_file = output_dir / output_template.format(
                device_id=device_id, state=state, depth=int(operating_depth))
            
            if skip_existing and out_file.exists():
                print(f"Skipping {state} Design {device_id}: exists")
                continue
            
            try:
                results = process_state(state, state_dir, device_id, power_surfaces_dir,
                                       operating_depth, fcr, min_median_speed)
                
                save_results(results, out_file, fcr=fcr,
                            resolution_degrees=resolution_degrees, resolution_km=resolution_km)
                
                valid = results['ValidSites']
                valid_lcoe = results['LCOE'][valid & (results['LCOE'] < np.inf)]
                mean_cf = np.mean(results['CapacityFactor'][valid])
                median_lcoe = np.median(valid_lcoe) if len(valid_lcoe) > 0 else np.inf
                
                print(f"{state} Design {device_id}: CF={mean_cf:.3f}, LCOE=${median_lcoe:.0f}/MWh")
                summaries.append({'state': state, 'device': device_id, 'mean_cf': mean_cf,
                                 'median_lcoe': median_lcoe, 'n_valid_sites': np.sum(valid)})
            except Exception as e:
                print(f"Error {state} Design {device_id}: {e}")
    
    return summaries