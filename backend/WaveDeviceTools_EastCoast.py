# WaveDeviceTools_EastCoast.py — v4 (2026-02-10)
# Generalized for East Coast: handles WPTO NPZ format, uses peak_period for Tp
# Added user-configurable depth and distance-to-shore filters
import csv
import numpy as np
import sys

def ReadTurbineData(TurbineFile):
    
    File_Turbine=open(TurbineFile, "r")
    File_Turbine_csv=csv.reader(File_Turbine,delimiter=',')
    MP_Matrix=[]    
    
    for EachLine in File_Turbine_csv:
        
        if File_Turbine_csv.line_num==2:
            RatedPower=float(EachLine[1])
            
        if File_Turbine_csv.line_num==3:
            E_Mec2El=float(EachLine[1])
    
        if File_Turbine_csv.line_num==4:
            E_Av=float(EachLine[1])
            
        if File_Turbine_csv.line_num==5:
            E_Tr=float(EachLine[1])
 
        if File_Turbine_csv.line_num==6:
            MinDepth=float(EachLine[1])

        if File_Turbine_csv.line_num==7:
            MaxDepth=float(EachLine[1])
            
        if File_Turbine_csv.line_num==10:
            Te_Bins=EachLine[1:]
            Te_Bins=np.array(Te_Bins,dtype=float)
            Te_Bins=Te_Bins.reshape(len(Te_Bins),1)
            
        if File_Turbine_csv.line_num>=11:
            MP_Matrix.append(np.array(EachLine,dtype=float))
    
    File_Turbine.close()
            
    MP_Matrix=np.array(MP_Matrix,dtype=float)
    Hs_Bins=MP_Matrix[:,0]
    Hs_Bins=Hs_Bins.reshape(len(Hs_Bins),1)
    MP_Matrix=MP_Matrix[:,1:]

    Turbine={"RatedPower":RatedPower,
         "E_Mec2El":E_Mec2El,
         "E_Av":E_Av,
         "E_Tr":E_Tr,
         "MinDepth":MinDepth,
         "MaxDepth":MaxDepth,         
         "Te_Bins":Te_Bins,
         "Hs_Bins":Hs_Bins,
         "MP_Matrix":MP_Matrix,
          }    

    return Turbine


def _load_wave_data(WaveDataPath):
    """
    Load wave data from NPZ file, handling both legacy key names
    (Hs, Tp, LatLong, Depth, DistanceShore, DateTimeList)
    and new East Coast key names
    (significant_wave_height, peak_period, coordinates, depth, time_index).
    
    Returns: HsNC, TpNC, LatLong, Depth, time_index
    All time-series arrays returned as (time, locations).
    """
    WaveFile = np.load(WaveDataPath, allow_pickle=True)
    keys = list(WaveFile.keys())
    
    # --- Wave Height ---
    if "significant_wave_height" in keys:
        HsNC = WaveFile["significant_wave_height"]
    elif "Hs" in keys:
        HsNC = WaveFile["Hs"]
    else:
        raise KeyError(f"No wave height key found. Available keys: {keys}")
    
    # --- Wave Period (prefer peak_period for Tp) ---
    if "peak_period" in keys:
        TpNC = WaveFile["peak_period"]
    elif "Tp" in keys:
        TpNC = WaveFile["Tp"]
    elif "energy_period" in keys:
        TpNC = WaveFile["energy_period"]
    else:
        raise KeyError(f"No wave period key found. Available keys: {keys}")
    
    # --- Coordinates ---
    if "coordinates" in keys:
        LatLong = WaveFile["coordinates"]
    elif "LatLong" in keys:
        LatLong = WaveFile["LatLong"]
    else:
        raise KeyError(f"No coordinate key found. Available keys: {keys}")
    
    # --- Depth ---
    if "depth" in keys:
        Depth = WaveFile["depth"]
    elif "Depth" in keys:
        Depth = WaveFile["Depth"]
    else:
        raise KeyError(f"No depth key found. Available keys: {keys}")
    
    # --- Time Index ---
    if "time_index" in keys:
        time_index = WaveFile["time_index"]
    elif "DateTimeList" in keys:
        time_index = WaveFile["DateTimeList"]
    else:
        time_index = None
    
    # --- Ensure correct orientation: (time, locations) ---
    # Depth has one value per location, so len(Depth) == number of locations
    if HsNC.ndim == 2:
        n_locations = len(Depth)
        if HsNC.shape[1] == n_locations:
            pass  # Already (time, locations) — correct
        elif HsNC.shape[0] == n_locations and HsNC.shape[1] != n_locations:
            # Data is (locations, time) -> transpose
            print(f"  Transposing wave data from ({HsNC.shape[0]}, {HsNC.shape[1]}) to (time, locations)")
            HsNC = HsNC.T
            TpNC = TpNC.T
        else:
            print(f"  WARNING: Cannot determine orientation. HsNC {HsNC.shape}, locations={n_locations}")
    
    print(f"  Wave data loaded: HsNC {HsNC.shape}, TpNC {TpNC.shape}, "
          f"Coords {LatLong.shape}, Depth {Depth.shape}")
    
    return HsNC, TpNC, LatLong, Depth, time_index


def GetEnergyPu(TrubineDataPath, WaveDataPath, MinDepthOverride=None, MaxDepthOverride=None,
                MinDistShore=None, MaxDistShore=None, InputDataPath=None, CoastlineShpPath=None):
    """
    Compute per-unit energy production for a WEC design at all valid locations.
    
    Parameters:
    -----------
    MinDepthOverride, MaxDepthOverride : float or None
        Override the turbine CSV depth limits. If None, uses values from CSV.
    MinDistShore, MaxDistShore : float or None (km)
        Filter by distance to shore. If None, no distance filter applied.
    InputDataPath : str or None
        Base path for data (used by GetDistanceToShore if distance filter is set)
    CoastlineShpPath : str or None
        Path to coastline shapefile (used if distance filter is set)
    
    Returns:
    --------
    Energy_pu : np.array (time, filtered_locations)
    LatLong : np.array (filtered_locations, 2)
    """
    Turbine = ReadTurbineData(TrubineDataPath)

    RatedPower = Turbine["RatedPower"]
    E_Mec2El = Turbine["E_Mec2El"]
    E_Av = Turbine["E_Av"]
    E_Tr = Turbine["E_Tr"]
    Te_Bins = Turbine["Te_Bins"]
    Hs_Bins = Turbine["Hs_Bins"]
    MP_Matrix = Turbine["MP_Matrix"]

    HsNC, TpNC, LatLong, Depth, _ = _load_wave_data(WaveDataPath)

    HsShape = HsNC.shape

    # Flatten, find nearest bin, reshape
    D1_HsNC = np.reshape(HsNC, (np.size(HsNC), 1))
    IdxHs = np.reshape(np.argmin(np.abs(D1_HsNC - Hs_Bins.T), axis=1), HsShape)

    D1_TpNC = np.reshape(TpNC, (np.size(TpNC), 1))
    IdxTp = np.reshape(np.argmin(np.abs(D1_TpNC - Te_Bins.T), axis=1), HsShape)

    EnergyProduction = np.minimum(MP_Matrix[IdxHs, IdxTp] * E_Mec2El, RatedPower)

    WakeEffect = 0.95
    EnergyPu = EnergyProduction / RatedPower * WakeEffect
    Energy_pu = EnergyPu * E_Av * E_Tr
    # Energy_pu is (time, locations) — same orientation as HsNC
    
    # --- Depth filter ---
    MinDepth = MinDepthOverride if MinDepthOverride is not None else Turbine["MinDepth"]
    MaxDepth = MaxDepthOverride if MaxDepthOverride is not None else Turbine["MaxDepth"]
    IdxIn = (Depth >= MinDepth) & (Depth <= MaxDepth)
    print(f"  Depth filter [{MinDepth}, {MaxDepth}]m: {np.sum(IdxIn)}/{len(Depth)} locations kept")
    
    Energy_pu = Energy_pu[:, IdxIn]
    LatLong = LatLong[IdxIn, :]
    Depth = Depth[IdxIn]
    
    # --- Distance to shore filter ---
    if MinDistShore is not None or MaxDistShore is not None:
        DistanceShore = _compute_distance_to_shore(LatLong, InputDataPath=InputDataPath, CoastlineShpPath=CoastlineShpPath)
        
        dist_mask = np.ones(len(DistanceShore), dtype=bool)
        if MinDistShore is not None:
            dist_mask &= (DistanceShore >= MinDistShore)
        if MaxDistShore is not None:
            dist_mask &= (DistanceShore <= MaxDistShore)
        
        print(f"  Distance filter [{MinDistShore}, {MaxDistShore}] km: {np.sum(dist_mask)}/{len(DistanceShore)} locations kept")
        Energy_pu = Energy_pu[:, dist_mask]
        LatLong = LatLong[dist_mask, :]
    
    print(f"  Final: Energy_pu {Energy_pu.shape}, LatLong {LatLong.shape}")
    return Energy_pu, LatLong


# ============================================================
# Cost model functions
# ============================================================

def ComputeAnnualCost_Pelamis(DistanceShoreToPlatform, TotalMorringChainLength=None, LengthCable34kV=None):
    NumTurbines = 100
    RatedPower = 1.5
    if LengthCable34kV is None:
        LengthCable34kV = NumTurbines * 1
    FCR = 11.3 / 100
    CAPEX_OC = 1269.6 + 1.003 * DistanceShoreToPlatform + 0.186 * LengthCable34kV
    OPEX_OC = 30.4868 + 0.025 * DistanceShoreToPlatform + 4.5e-3 * LengthCable34kV
    AnnCost = CAPEX_OC * FCR + OPEX_OC
    return AnnCost, CAPEX_OC, OPEX_OC


def ComputeAnnualCost_RM3(DistanceShoreToPlatform, TotalMorringChainLength=None, LengthCable34kV=None):
    NumTurbines = 100
    RatedPower = 0.286
    if LengthCable34kV is None:
        LengthCable34kV = NumTurbines * 1
    FCR = 11.3 / 100
    CAPEX_OC = 389794193 * 1e-6
    OPEX_OC = 9358840 * 1e-6
    AnnCost = CAPEX_OC * FCR + OPEX_OC
    return AnnCost, CAPEX_OC, OPEX_OC


def ComputeAnnualCost_Full_Scale(DistanceShoreToPlatform, TotalMorringChainLength=None, LengthCable34kV=None):
    NumTurbines = 100
    RatedPower = 0.572
    if LengthCable34kV is None:
        LengthCable34kV = NumTurbines * 1
    FCR = 10.8 / 100
    CAPEX_OC = 636630863.49 * 1e-6
    OPEX_OC = 9665632.60 * 1e-6
    AnnCost = CAPEX_OC * FCR + OPEX_OC
    return AnnCost, CAPEX_OC, OPEX_OC


def ComputeAnnualCost_Half_Scale(DistanceShoreToPlatform, TotalMorringChainLength=None, LengthCable34kV=None):
    NumTurbines = 100
    RatedPower = 0.12723
    if LengthCable34kV is None:
        LengthCable34kV = NumTurbines * 1
    FCR = 10.8 / 100
    CAPEX_OC = 166655714 * 1e-6
    OPEX_OC = 3080731 * 1e-6
    AnnCost = CAPEX_OC * FCR + OPEX_OC
    return AnnCost, CAPEX_OC, OPEX_OC


def ComputeAnnualCost_OneThird_Scale(DistanceShoreToPlatform, TotalMorringChainLength=None, LengthCable34kV=None):
    NumTurbines = 100
    RatedPower = 0.034084
    if LengthCable34kV is None:
        LengthCable34kV = NumTurbines * 1
    FCR = 10.8 / 100
    CAPEX_OC = 68612908 * 1e-6
    OPEX_OC = 1701624 * 1e-6
    AnnCost = CAPEX_OC * FCR + OPEX_OC
    return AnnCost, CAPEX_OC, OPEX_OC


def ComputeAnnualCost_Bora_RM3(DistanceShoreToPlatform, TotalMorringChainLength=None, LengthCable34kV=None):
    NumTurbines = 100
    RatedPower = 1.0
    if LengthCable34kV is None:
        LengthCable34kV = NumTurbines * 1
    FCR = 10.8 / 100
    CAPEX_OC = 383000000 * 1e-6
    OPEX_OC = 5500000 * 1e-6
    AnnCost = CAPEX_OC * FCR + OPEX_OC
    return AnnCost, CAPEX_OC, OPEX_OC


# ============================================================
# Distance to shore
# ============================================================

def _compute_distance_to_shore(LatLong, InputDataPath=None, CoastlineShpPath=None):
    """
    Compute distance to shore (km) for each point in LatLong.
    Uses GetDistanceToShore from GeneralGeoTools_EastCoast if available.
    """
    try:
        from GeneralGeoTools_EastCoast import GetDistanceToShore
        if InputDataPath is None:
            InputDataPath = "."
        return GetDistanceToShore(InputDataPath, LatLong, CoastlineShpPath=CoastlineShpPath)
    except ImportError:
        print("  WARNING: GeneralGeoTools_EastCoast not found. Using rough distance estimate.")
        lat_rad = np.radians(LatLong[:, 0])
        dist_deg = np.abs(LatLong[:, 1] - (-75.0))
        dist_km = dist_deg * 111 * np.cos(lat_rad)
        return np.abs(dist_km)


# ============================================================
# Main cost + generation function
# ============================================================

def GetCostAndGenerationWaveTurbine(TrubineDataPath, WaveDataPath, TurbineName="Pelamis",
                                     SavePath=None, Discount=1,
                                     InputDataPath=None, CoastlineShpPath=None,
                                     MinDepthOverride=None, MaxDepthOverride=None,
                                     MinDistShore=None, MaxDistShore=None):
    """
    Compute cost and energy generation for a WEC design across all valid sites.
    
    Parameters:
    -----------
    MinDepthOverride, MaxDepthOverride : float or None
        Override the turbine CSV depth limits. If None, uses turbine CSV values.
    MinDistShore, MaxDistShore : float or None (km)
        Filter by distance to shore. If None, no distance filter applied.
    InputDataPath : str or None - Base data path for distance-to-shore calculation
    CoastlineShpPath : str or None - Path to coastline shapefile
    """
    HsNC_raw, TpNC_raw, LatLong_raw, Depth_raw, TimeList = _load_wave_data(WaveDataPath)
    
    # Compute raw resource: Energy Flux [kW/m]  — (time, locations)
    EnergyFlux = 0.5 * (HsNC_raw ** 2) * TpNC_raw
    RawResource = EnergyFlux

    TurbineData = ReadTurbineData(TrubineDataPath)
    
    # Get Energy_pu with same filters
    Energy_pu, LatLong_filtered = GetEnergyPu(
        TrubineDataPath, WaveDataPath,
        MinDepthOverride=MinDepthOverride, MaxDepthOverride=MaxDepthOverride,
        MinDistShore=MinDistShore, MaxDistShore=MaxDistShore,
        InputDataPath=InputDataPath, CoastlineShpPath=CoastlineShpPath
    )
    
    # Apply the same filters to Depth, RawResource, DistanceShore
    MinDepth = MinDepthOverride if MinDepthOverride is not None else TurbineData["MinDepth"]
    MaxDepth = MaxDepthOverride if MaxDepthOverride is not None else TurbineData["MaxDepth"]
    
    depth_mask = (Depth_raw >= MinDepth) & (Depth_raw <= MaxDepth)
    Depth = Depth_raw[depth_mask]
    LatLong_depth = LatLong_raw[depth_mask, :]
    RawResource = RawResource[:, depth_mask]
    
    # Distance to shore
    WaveFile = np.load(WaveDataPath, allow_pickle=True)
    wave_keys = list(WaveFile.keys())
    if "DistanceShore" in wave_keys:
        DistanceShore = WaveFile["DistanceShore"][depth_mask]
    else:
        print("  Computing distance to shore for cost model...")
        DistanceShore = _compute_distance_to_shore(LatLong_depth, InputDataPath=InputDataPath, CoastlineShpPath=CoastlineShpPath)
    
    # Apply distance filter if specified
    if MinDistShore is not None or MaxDistShore is not None:
        dist_mask = np.ones(len(DistanceShore), dtype=bool)
        if MinDistShore is not None:
            dist_mask &= (DistanceShore >= MinDistShore)
        if MaxDistShore is not None:
            dist_mask &= (DistanceShore <= MaxDistShore)
        
        Depth = Depth[dist_mask]
        LatLong = LatLong_depth[dist_mask, :]
        DistanceShore = DistanceShore[dist_mask]
        RawResource = RawResource[:, dist_mask]
    else:
        LatLong = LatLong_depth

    # --- Cost model ---
    cost_functions = {
        "Pelamis": ComputeAnnualCost_Pelamis,
        "RM3": ComputeAnnualCost_RM3,
        "Full_Scale": ComputeAnnualCost_Full_Scale,
        "Half_Scale": ComputeAnnualCost_Half_Scale,
        "OneThird_Scale": ComputeAnnualCost_OneThird_Scale,
        "Bora_RM3": ComputeAnnualCost_Bora_RM3,
    }
    
    if TurbineName not in cost_functions:
        raise ValueError(f"Unknown TurbineName '{TurbineName}'. Options: {list(cost_functions.keys())}")
    
    cost_func = cost_functions[TurbineName]

    AnnualizedCost = []
    CAPEX_site = []
    OPEX_site = []

    for i in range(len(Depth)):
        TotalMorringChainLength = Depth[i] * 100 / 1000  # km
        DistanceShoreToPlatform = DistanceShore[i]
        
        UnitCost_ann, CAPEX_OC, OPEX_OC = cost_func(DistanceShoreToPlatform, TotalMorringChainLength)
        UnitCost_ann = UnitCost_ann / 100
        AnnualizedCost.append(UnitCost_ann)
        CAPEX_site.append(CAPEX_OC / 100)
        OPEX_site.append(OPEX_OC / 100)

    NumberOfCellsPerSite = [1] * len(Depth)
    RatedPower = TurbineData["RatedPower"] / 1e6  # MW
    ResolutionKm = -1
    DistanceShore = np.array(DistanceShore)
    CAPEX_site = np.array(CAPEX_site) / Discount
    OPEX_site = np.array(OPEX_site) / Discount
    AnnualizedCost = np.array(AnnualizedCost) / Discount
    
    LCOE_UDS_MWH = AnnualizedCost * 1e6 / (RatedPower * 365 * 24 * np.mean(Energy_pu, axis=0))
    
    print(f"  Output: {len(Depth)} sites, RatedPower={RatedPower:.4f} MW")
    
    if SavePath is not None:
        np.savez(SavePath,
            ReadMe=None,
            Energy_pu=Energy_pu.astype(np.float16),
            RatedPower=RatedPower,
            LatLong=LatLong.astype(np.float32),
            Depth=Depth,
            DistanceShore=DistanceShore.astype(np.float16),
            CAPEX_site=CAPEX_site.astype(np.float16),
            OPEX_site=OPEX_site.astype(np.float16),
            AnnualizedCost=AnnualizedCost.astype(np.float16),
            RawResource=RawResource.astype(np.float16),
            TimeList=TimeList,
            NumberOfCellsPerSite=NumberOfCellsPerSite,
            ResolutionKm=ResolutionKm,
            ResolutionDegrees=-1,
            LCOE=LCOE_UDS_MWH
        )
    else:
        return Energy_pu, RatedPower, LatLong, Depth, DistanceShore, CAPEX_site, OPEX_site, AnnualizedCost, TimeList, NumberOfCellsPerSite, LCOE_UDS_MWH


# Legacy alias
def GetCostAndGenerationWaveTurbine_Pelamis(TrubineDataPath, WaveDataPath, TurbineName="Pelamis",
                                             SavePath=None, Discount=1, InputDataPath=None, CoastlineShpPath=None,
                                             MinDepthOverride=None, MaxDepthOverride=None,
                                             MinDistShore=None, MaxDistShore=None):
    return GetCostAndGenerationWaveTurbine(
        TrubineDataPath, WaveDataPath, TurbineName=TurbineName, SavePath=SavePath,
        Discount=Discount, InputDataPath=InputDataPath, CoastlineShpPath=CoastlineShpPath,
        MinDepthOverride=MinDepthOverride, MaxDepthOverride=MaxDepthOverride,
        MinDistShore=MinDistShore, MaxDistShore=MaxDistShore
    )
