4#This code compute the optimal portfolio for wave wind and ocean current resources
#Considering transmission system costs, CAPEX and OPEX of each technology and its generation availability in a given region

#The objective function is the maximization of the total generation of the portfolio, costraint to limits in the portfolio LCOE, maximum
#Capacity of the transmission system, maximum number of turbines per site location, and maxmimum radious of the energy collection system.

#The model also takes into considering curtailment, and the possibility of chosing from a limited number of turbine designs.

#env Gurobi
import numpy as np
from pyomo.environ import *
import pandas as pd
from datetime import datetime, timedelta
from tqdm import tqdm
import sys
import os
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from  GetIdxInOutRadious import GetIdxOutRadious, GetIdxInRadious_Simple
from Port_Opt_Tools import GetOverlaps_Idx_Area

windCostScaling = 1.0 #0.8, 1.0, 1.2 for sensitivity analysis +-20%
kiteCostScaling = 1.0 #0.8, 1.0, 1.2 ""
transmissionCostScaling = 1.0 #0.8, 1.0, 1.2 ""

def PreparePotOptInputs(PathWindDesigns, PathWaveDesigns, PathKiteDesigns, PathTransmissionDesign, LCOE_RANGE=range(200,30,-2)\
    ,Max_CollectionRadious=30, MaxDesignsWind=1, MaxDesignsWave=1, MaxDesignsKite=1, MinNumWindTurb=0, MinNumWaveTurb=0, MinNumKiteTrub=0,
    WindTurbinesPerSite=4, KiteTurbinesPerSite=390, WaveTurbinesPerSite=300):
    
    
    # WindTurbinesPerSite= 4 [MW/Km2]
    # KiteTurbinesPerSite= 25 per 2x2km cells, but the simulation is running on 0.08x0.08 degrees cells (as base resolution)
    # KiteTurbinesPerSite= 390 per 9x7km cells
    # WaveTurbinesPerSite=  1/15degees , from pelamis 12.5 devices per km2. This would be +500 devices, using 300 for now

    #WindTurbinesPerSite: Number of turbines per site location based on the initial wind resolution from NREL
    #KiteTurbinesPerSite: Number of turbines per site location based on the initial kite resolution from where the data was obtained (HYCOM, MABSAB)
    #WaveTurbinesPerSite: Number of turbines per site location based on the initial wave resolution from where the data was obtained (WWIII)  
    
    #Function to prepare the inputs for the optimization
    #All portfolio data needs to be at the same time resolution and range, unless the portfolio path is empty eg. PathWaveDesigns=[]
    # LCOE_RANGE=range(200,30,-2) #Max LCOE limits investigated
    # Max_CollectionRadious=30 #Radious for the energy collection system

    # TimeList will be set from the first technology that has data
    TimeList = None

    WindEnergy, WindLatLong, AnnualizedCostWind, MaxNumWindPerSite, WindDesign, TimeWindData,\
    RatedPowerWindTurbine, WindResolutionDegrees, WindResolutionKm = list(), list(), list(), list(), list(), list(), list(), list(), list()
    
    KiteEnergy, KiteLatLong, AnnualizedCostKite, MaxNumKitePerSite, KiteDesign, TimeKiteData,\
    RatedPowerKiteTurbine, KiteResolutionDegrees, KiteResolutionKm = list(), list(), list(), list(), list(), list(), list(), list(), list()
    
    WaveEnergy, WaveLatLong, AnnualizedCostWave, MaxNumWavePerSite, WaveDesign, TimeWaveData,\
    RatedPowerWaveTurbine, WaveResolutionDegrees, WaveResolutionKm = list(), list(), list(), list(), list(), list(), list(), list(), list()
    
    for i in range(len(PathWindDesigns)):
        Data=np.load(PathWindDesigns[i],allow_pickle=True)
        if i==0:
            
            WindEnergy=Data['Energy_pu']
            WindLatLong=Data['LatLong']
            AnnualizedCostWind=Data['AnnualizedCost']
            AnnualizedCostWind=AnnualizedCostWind*windCostScaling

            WindDesign=np.array([i]*len(Data["NumberOfCellsPerSite"]))
            TimeWindData=Data["TimeList"]
            RatedPowerWindTurbine=np.array([float(Data["RatedPower"])]*len(Data["NumberOfCellsPerSite"]))
            WindResolutionDegrees=np.array([float(Data["ResolutionDegrees"])]*len(Data["NumberOfCellsPerSite"]))
            WindResolutionKm=np.array([float(Data["ResolutionKm"])]*len(Data["NumberOfCellsPerSite"]))
            
            # ORIGINAL: Computed max turbines from density (MW/km²) and grid cell aggregation.
            # WindTurbinesPerSite was a density (MW/km²), multiplied by ~4 km² cell area,
            # divided by turbine rated power to get devices per original grid cell.
            # Then multiplied by NumberOfCellsPerSite (how many raw grid cells were
            # aggregated into this site during preprocessing) to get total devices allowed.
            # This approach broke down after spatial resampling set NumberOfCellsPerSite=1.
            #TubPerSite=np.max([WindTurbinesPerSite*4/float(Data["RatedPower"]),1])
            #MaxNumWindPerSite=Data["NumberOfCellsPerSite"]*TubPerSite
            
            # NEW: WindTurbinesPerSite from config is used directly as the max devices per site.
            MaxNumWindPerSite=np.array([WindTurbinesPerSite]*len(Data["NumberOfCellsPerSite"]))
            
            if TimeList is None:
                TimeList=TimeWindData
            
            
        else:
            WindEnergy=np.concatenate((WindEnergy,Data['Energy_pu']),axis=1)
            WindLatLong=np.concatenate((WindLatLong,Data['LatLong']))
            AnnualizedCostWind=np.concatenate((AnnualizedCostWind,Data['AnnualizedCost']))
            
            WindDesign=np.concatenate((WindDesign,[i]*len(Data["NumberOfCellsPerSite"])))
            RatedPowerWindTurbine=np.concatenate((RatedPowerWindTurbine,np.array([float(Data["RatedPower"])]*len(Data["NumberOfCellsPerSite"]))))
            WindResolutionDegrees=np.concatenate((WindResolutionDegrees, np.array([float(Data["ResolutionDegrees"])]*len(Data["NumberOfCellsPerSite"]))))
            WindResolutionKm=np.concatenate((WindResolutionKm, np.array([float(Data["ResolutionKm"])]*len(Data["NumberOfCellsPerSite"]))))

            # ORIGINAL: Same density-based calculation for additional wind designs.
            #TubPerSite=np.max([(WindTurbinesPerSite*4/float(Data["RatedPower"])),1])     
            #MaxNumWindPerSite=np.concatenate((MaxNumWindPerSite,Data["NumberOfCellsPerSite"]*TubPerSite))
            
            # NEW: Direct config value.
            MaxNumWindPerSite=np.concatenate((MaxNumWindPerSite,np.array([WindTurbinesPerSite]*len(Data["NumberOfCellsPerSite"]))))
            
        Data.close()
        
    #Kite Data
    for i in range(len(PathKiteDesigns)):
        Data=np.load(PathKiteDesigns[i],allow_pickle=True)
        if i==0:
            KiteEnergy=Data['Energy_pu'][:-8,:] #Change it in the future
            KiteLatLong=Data['LatLong']
            AnnualizedCostKite=Data['AnnualizedCost']
            AnnualizedCostKite=AnnualizedCostKite*kiteCostScaling #Sensitivity analysis on costs

            # ORIGINAL: Multiplied device density by NumberOfCellsPerSite, which tracked
            # how many raw grid cells (from HYCOM/MABSAB source data) were aggregated
            # into each site. After spatial resampling, NumberOfCellsPerSite=1, making
            # this multiplication ineffective.
            #MaxNumKitePerSite=Data["NumberOfCellsPerSite"]*KiteTurbinesPerSite
            
            # NEW: KiteTurbinesPerSite from config is used directly as the max devices per site.
            MaxNumKitePerSite=np.array([KiteTurbinesPerSite]*len(Data["NumberOfCellsPerSite"]))
            KiteDesign=np.array([i]*len(Data["NumberOfCellsPerSite"]))
            TimeKiteData=Data["TimeList"][:-8]
            RatedPowerKiteTurbine=np.array([float(Data["RatedPower"])]*len(Data["NumberOfCellsPerSite"]))
            KiteResolutionDegrees=np.array([float(Data["ResolutionDegrees"])]*len(Data["NumberOfCellsPerSite"]))
            KiteResolutionKm=np.array([float(Data["ResolutionKm"])]*len(Data["NumberOfCellsPerSite"]))
            
            if TimeList is None:
                TimeList=TimeKiteData
            
            
        else:
            KiteEnergy=np.concatenate((KiteEnergy,Data['Energy_pu'][:-8,:]),axis=1) #Change it in the future
            KiteLatLong=np.concatenate((KiteLatLong,Data['LatLong']))
            print(Data['AnnualizedCost'])
            AnnualizedCostKite=np.concatenate((AnnualizedCostKite,Data['AnnualizedCost']))
            # ORIGINAL: Same cell-aggregation scaling for additional kite designs.
            #MaxNumKitePerSite=np.concatenate((MaxNumKitePerSite,KiteTurbinesPerSite*Data["NumberOfCellsPerSite"]))
            
            # NEW: Direct config value.
            MaxNumKitePerSite=np.concatenate((MaxNumKitePerSite,np.array([KiteTurbinesPerSite]*len(Data["NumberOfCellsPerSite"]))))
            KiteDesign=np.concatenate((KiteDesign,[i]*len(Data["NumberOfCellsPerSite"])))
            RatedPowerKiteTurbine=np.concatenate((RatedPowerKiteTurbine,np.array([float(Data["RatedPower"])]*len(Data["NumberOfCellsPerSite"]))))
            KiteResolutionDegrees=np.concatenate((KiteResolutionDegrees, np.array([float(Data["ResolutionDegrees"])]*len(Data["NumberOfCellsPerSite"]))))
            KiteResolutionKm=np.concatenate((KiteResolutionKm, np.array([float(Data["ResolutionKm"])]*len(Data["NumberOfCellsPerSite"]))))
            
        Data.close()
        
    #Wave Data
    for i in range(len(PathWaveDesigns)):
        Data=np.load(PathWaveDesigns[i],allow_pickle=True)
        if i==0:
            WaveEnergy=Data['Energy_pu']
            WaveLatLong=Data['LatLong']
            AnnualizedCostWave=Data['AnnualizedCost']
            # ORIGINAL: Multiplied device density by NumberOfCellsPerSite, which tracked
            # how many raw WWIII grid cells were aggregated into each site. After spatial
            # resampling to a uniform grid, NumberOfCellsPerSite=1, so this always
            # collapsed to just WaveTurbinesPerSite.
            #MaxNumWavePerSite=Data["NumberOfCellsPerSite"]*WaveTurbinesPerSite
            
            # NEW: WaveTurbinesPerSite from config is used directly as the max devices per site.
            MaxNumWavePerSite=np.array([WaveTurbinesPerSite]*len(Data["NumberOfCellsPerSite"]))
            WaveDesign=np.array([i]*len(Data["NumberOfCellsPerSite"]))
            TimeWaveData=Data["TimeList"]
            RatedPowerWaveTurbine=np.array([float(Data["RatedPower"])]*len(Data["NumberOfCellsPerSite"]))  
            WaveResolutionDegrees=np.array([float(Data["ResolutionDegrees"])]*len(Data["NumberOfCellsPerSite"]))
            WaveResolutionKm=np.array([float(Data["ResolutionKm"])]*len(Data["NumberOfCellsPerSite"]))
            
            if TimeList is None:
                TimeList=TimeWaveData
            
        else:
            WaveEnergy=np.concatenate((WaveEnergy,Data['Energy_pu']),axis=1)
            WaveLatLong=np.concatenate((WaveLatLong,Data['LatLong']))
            AnnualizedCostWave=np.concatenate((AnnualizedCostWave,Data['AnnualizedCost']))
            # ORIGINAL: Same cell-aggregation scaling for additional wave designs.
            #MaxNumWavePerSite=np.concatenate((MaxNumWavePerSite,WaveTurbinesPerSite*Data["NumberOfCellsPerSite"]))
            
            # NEW: Direct config value.
            MaxNumWavePerSite=np.concatenate((MaxNumWavePerSite,np.array([WaveTurbinesPerSite]*len(Data["NumberOfCellsPerSite"]))))
            WaveDesign=np.concatenate((WaveDesign,[i]*len(Data["NumberOfCellsPerSite"])))
            RatedPowerWaveTurbine=np.concatenate((RatedPowerWaveTurbine,np.array([float(Data["RatedPower"])]*len(Data["NumberOfCellsPerSite"]))))
            WaveResolutionDegrees=np.concatenate((WaveResolutionDegrees, np.array([float(Data["ResolutionDegrees"])]*len(Data["NumberOfCellsPerSite"]))))
            WaveResolutionKm=np.concatenate((WaveResolutionKm, np.array([float(Data["ResolutionKm"])]*len(Data["NumberOfCellsPerSite"]))))

    # #Verify if all the data is at the same time resolution and range
    # if len(PathWindDesigns)!=0 and len(PathKiteDesigns)!=0:
        
    #     if np.all(TimeWindData==TimeKiteData)==False:
    #         return print("Time resolution of the wind, and wave data is not the same")
        
    # if len(PathWindDesigns)!=0 and len(PathWaveDesigns)!=0:
    #     if  np.all(TimeWindData==TimeWaveData)==False:
    #         return print("Time resolution of the wind, and wave data is not the same")

    # if len(PathKiteDesigns)!=0 and len(PathWaveDesigns)!=0:
    #     if  np.all(TimeKiteData==TimeWaveData)==False:
    #         return print("Time resolution of the kite, and wave data is not the same")

    # Validate that at least one technology has been specified
    if TimeList is None:
        raise ValueError("At least one technology (wind, wave, or kite) must be specified with design paths.")
    
    # ---------------------------------------------------------------------------
    # Temporal resolution alignment
    # Different technologies may have different time resolutions (e.g., wind=1hr,
    # wave=3hr). Detect the coarsest resolution from loaded TimeLists and 
    # downsample finer-resolution technologies to match by striding.
    # ---------------------------------------------------------------------------
    
    # Collect (timestep_count, TimeList, label) for each loaded technology
    _time_info = []
    if len(PathWindDesigns) > 0:
        _time_info.append((WindEnergy.shape[0], TimeWindData, "Wind"))
    if len(PathKiteDesigns) > 0:
        _time_info.append((KiteEnergy.shape[0], TimeKiteData, "Kite"))
    if len(PathWaveDesigns) > 0:
        _time_info.append((WaveEnergy.shape[0], TimeWaveData, "Wave"))
    
    # Find the coarsest resolution (fewest timesteps = largest time step)
    coarsest_count = min(info[0] for info in _time_info)
    
    # Downsample any technology with more timesteps
    for count, tdata, label in _time_info:
        if count > coarsest_count:
            ratio = count // coarsest_count
            if count % coarsest_count != 0:
                print(f"  WARNING: {label} timesteps ({count}) not evenly divisible by target ({coarsest_count}). Truncating before stride.")
            
            print(f"  Downsampling {label} from {count} to {coarsest_count} timesteps (stride={ratio})")
            
            if label == "Wind":
                WindEnergy = WindEnergy[::ratio, :]
                TimeWindData = TimeWindData[::ratio]
            elif label == "Kite":
                KiteEnergy = KiteEnergy[::ratio, :]
                TimeKiteData = TimeKiteData[::ratio]
            elif label == "Wave":
                WaveEnergy = WaveEnergy[::ratio, :]
                TimeWaveData = TimeWaveData[::ratio]
    
    # Set TimeList from the coarsest technology
    for count, tdata, label in _time_info:
        if count == coarsest_count:
            TimeList = tdata
            break
    
    # Final trim in case striding left an off-by-one
    timestep_counts = []
    if len(PathWindDesigns) > 0:
        timestep_counts.append(WindEnergy.shape[0])
    if len(PathKiteDesigns) > 0:
        timestep_counts.append(KiteEnergy.shape[0])
    if len(PathWaveDesigns) > 0:
        timestep_counts.append(WaveEnergy.shape[0])
    
    NumTimeSteps = min(timestep_counts)
    TimeList = TimeList[:NumTimeSteps]
    
    if len(PathWindDesigns) > 0:
        WindEnergy = WindEnergy[:NumTimeSteps, :]
    if len(PathKiteDesigns) > 0:
        KiteEnergy = KiteEnergy[:NumTimeSteps, :]
    if len(PathWaveDesigns) > 0:
        WaveEnergy = WaveEnergy[:NumTimeSteps, :]
    
    print(f"  All technologies aligned to {NumTimeSteps} timesteps")
    
    # Initialize proper empty numpy arrays for any technology that has no designs,
    # so that downstream code (variables, constraints, sums) can iterate over range(0) safely.
    if len(PathWindDesigns) == 0:
        WindEnergy = np.empty((NumTimeSteps, 0))
        WindLatLong = np.empty((0, 2))
        AnnualizedCostWind = np.empty(0)
        MaxNumWindPerSite = np.empty(0)
        WindDesign = np.empty(0, dtype=int)
        RatedPowerWindTurbine = np.empty(0)
        WindResolutionDegrees = np.empty(0)
        WindResolutionKm = np.empty(0)
    
    if len(PathKiteDesigns) == 0:
        KiteEnergy = np.empty((NumTimeSteps, 0))
        KiteLatLong = np.empty((0, 2))
        AnnualizedCostKite = np.empty(0)
        MaxNumKitePerSite = np.empty(0)
        KiteDesign = np.empty(0, dtype=int)
        RatedPowerKiteTurbine = np.empty(0)
        KiteResolutionDegrees = np.empty(0)
        KiteResolutionKm = np.empty(0)
    
    if len(PathWaveDesigns) == 0:
        WaveEnergy = np.empty((NumTimeSteps, 0))
        WaveLatLong = np.empty((0, 2))
        AnnualizedCostWave = np.empty(0)
        MaxNumWavePerSite = np.empty(0)
        WaveDesign = np.empty(0, dtype=int)
        RatedPowerWaveTurbine = np.empty(0)
        WaveResolutionDegrees = np.empty(0)
        WaveResolutionKm = np.empty(0)

    

    #Transmission
    Data=np.load(PathTransmissionDesign,allow_pickle=True)["TransmissionLineParameters"].item()

    AnnualizedCostTransmission=Data['S_BestACost']
    TransLatLong=Data['TL_LatLong']
    EfficiencyTransmission=Data['S_Efficiency']
    RatedPowerMWTransmissionMW=Data['RatedPowerMW']


    #Site counts are now derived directly from the LatLong arrays (which are proper
    #numpy arrays even when empty, thanks to the initialization above).

    PortImputDir={  #Wind data
                    "WindEnergy":WindEnergy,
                    "WindLatLong":WindLatLong,
                    "AnnualizedCostWind":AnnualizedCostWind, #Costs should be in M$/year
                    "MaxNumWindPerSite":MaxNumWindPerSite,
                    "WindDesign":WindDesign,
                    "RatedPowerWindTurbine":RatedPowerWindTurbine, #shoud be in MW
                    "NumWindSites": len(WindLatLong),
                    "WindResolutionDegrees":WindResolutionDegrees,
                    "WindResolutionKm":WindResolutionKm,
                    
                    
                    #Kite data
                    "KiteEnergy":KiteEnergy,
                    "KiteLatLong":KiteLatLong,
                    "AnnualizedCostKite":AnnualizedCostKite,
                    "MaxNumKitePerSite":MaxNumKitePerSite,
                    "KiteDesign":KiteDesign,
                    "RatedPowerKiteTurbine":RatedPowerKiteTurbine,
                    "NumKiteSites": len(KiteLatLong),
                    "KiteResolutionDegrees":KiteResolutionDegrees,
                    "KiteResolutionKm":KiteResolutionKm,

                                                     
                    #Wavedata
                    "WaveEnergy":WaveEnergy,
                    "WaveLatLong":WaveLatLong,
                    "AnnualizedCostWave":AnnualizedCostWave,
                    "MaxNumWavePerSite":MaxNumWavePerSite,
                    "WaveDesign":WaveDesign,
                    "RatedPowerWaveTurbine":RatedPowerWaveTurbine,
                    "NumWaveSites": len(WaveLatLong),
                    "WaveResolutionDegrees":WaveResolutionDegrees,
                    "WaveResolutionKm":WaveResolutionKm,
                    
                    
                    "TimeList":TimeList,
                    "NumTimeSteps":len(TimeList),
                    
                    #Transmission
                    "RatedPowerMWTransmissionMW":RatedPowerMWTransmissionMW,
                    "AnnualizedCostTransmission":AnnualizedCostTransmission,
                    "TransLatLong":TransLatLong,
                    "EfficiencyTransmission":EfficiencyTransmission,
                    "NumTransSites": len(TransLatLong),
                    
                    #Optimization Params
                    "LCOE_RANGE":LCOE_RANGE,
                    "Max_CollectionRadious":Max_CollectionRadious,
                    "MaxDesignsWind":MaxDesignsWind,
                    "MaxDesignsWave":MaxDesignsWave,
                    "MaxDesignsKite":MaxDesignsKite,
                    "MinNumWindTurb":MinNumWindTurb,
                    "MinNumWaveTurb":MinNumWaveTurb,
                    "MinNumKiteTrub":MinNumKiteTrub,
                
                }
    return PortImputDir

def SolvePortOpt_MaxGen_Model(PathWindDesigns, PathWaveDesigns, PathKiteDesigns, PathTransmissionDesign, LCOE_RANGE\
    ,Max_CollectionRadious,MaxDesignsWind, MaxDesingsWave, MaxDesingsKite,MinNumWindTurb,MinNumWaveTurb,MinNumKiteTrub,
    WindTurbinesPerSite=4, WaveTurbinesPerSite=300, KiteTurbinesPerSite=390):


    #Create and solve the optimization problem
    InputDir=PreparePotOptInputs(PathWindDesigns, PathWaveDesigns,PathKiteDesigns, PathTransmissionDesign, LCOE_RANGE\
        ,Max_CollectionRadious,MaxDesignsWind, MaxDesingsWave, MaxDesingsKite,MinNumWindTurb,MinNumWaveTurb,MinNumKiteTrub,
        WindTurbinesPerSite=WindTurbinesPerSite, WaveTurbinesPerSite=WaveTurbinesPerSite, KiteTurbinesPerSite=KiteTurbinesPerSite)

    NumWindDesigns=len(PathWindDesigns)
    NumWaveDesigns=len(PathWaveDesigns)
    NumKiteDesigns=len(PathKiteDesigns)

    Model = ConcreteModel()
    BigM=1000 #Big M for the maximum total number of turbines allowed to be installed

    # =========================================================================
    # Technology registry — defines each tech generically so we can loop
    # =========================================================================
    # Each entry maps a tech name to its InputDir keys, design count, and limits.
    # Only technologies with designs > 0 will have active variables & constraints.
    
    TECH_DEFS = [
        {"name": "Wind", "num_designs": NumWindDesigns,
         "energy_key": "WindEnergy",   "latlong_key": "WindLatLong",
         "cost_key": "AnnualizedCostWind", "maxnum_key": "MaxNumWindPerSite",
         "design_key": "WindDesign",   "power_key": "RatedPowerWindTurbine",
         "numsites_key": "NumWindSites",
         "reskm_key": "WindResolutionKm", "resdeg_key": "WindResolutionDegrees",
         "max_designs": InputDir["MaxDesignsWind"], "min_turbines": InputDir["MinNumWindTurb"]},
        {"name": "Wave", "num_designs": NumWaveDesigns,
         "energy_key": "WaveEnergy",   "latlong_key": "WaveLatLong",
         "cost_key": "AnnualizedCostWave", "maxnum_key": "MaxNumWavePerSite",
         "design_key": "WaveDesign",   "power_key": "RatedPowerWaveTurbine",
         "numsites_key": "NumWaveSites",
         "reskm_key": "WaveResolutionKm", "resdeg_key": "WaveResolutionDegrees",
         "max_designs": InputDir["MaxDesignsWave"], "min_turbines": InputDir["MinNumWaveTurb"]},
        {"name": "Kite", "num_designs": NumKiteDesigns,
         "energy_key": "KiteEnergy",   "latlong_key": "KiteLatLong",
         "cost_key": "AnnualizedCostKite", "maxnum_key": "MaxNumKitePerSite",
         "design_key": "KiteDesign",   "power_key": "RatedPowerKiteTurbine",
         "numsites_key": "NumKiteSites",
         "reskm_key": "KiteResolutionKm", "resdeg_key": "KiteResolutionDegrees",
         "max_designs": InputDir["MaxDesignsKite"], "min_turbines": InputDir["MinNumKiteTrub"]},
    ]
    
    # Filter to active technologies only
    active_techs = [t for t in TECH_DEFS if t["num_designs"] > 0]
    all_tech_names = [t["name"] for t in TECH_DEFS]  # Wind, Wave, Kite — always in this order
    
    # =========================================================================
    # Create Variables — always create all three Y and W vars (range(0) is fine for inactive)
    # This preserves the Model.Y_Wind / Y_Wave / Y_Kite interface for the rest of the code.
    # =========================================================================
    Model.Y_Wind = Var(range(InputDir["NumWindSites"]), domain=NonNegativeIntegers)
    Model.Y_Wave = Var(range(InputDir["NumWaveSites"]), domain=NonNegativeIntegers)
    Model.Y_Kite = Var(range(InputDir["NumKiteSites"]), domain=NonNegativeIntegers)
    
    Model.W_Wind = Var(range(NumWindDesigns), domain=Binary)
    Model.W_Wave = Var(range(NumWaveDesigns), domain=Binary)
    Model.W_Kite = Var(range(NumKiteDesigns), domain=Binary)
    
    Model.s     = Var(range(InputDir["NumTransSites"]), domain=Binary)
    Model.Delta = Var(range(InputDir["NumTimeSteps"]),  domain=NonNegativeReals)
    
    # Map tech names to their Pyomo variables for generic access
    Y_vars = {"Wind": Model.Y_Wind, "Wave": Model.Y_Wave, "Kite": Model.Y_Kite}
    W_vars = {"Wind": Model.W_Wind, "Wave": Model.W_Wave, "Kite": Model.W_Kite}
    
    # =========================================================================
    # Objective Function — sum over all techs generically
    # =========================================================================
    def objective_rule(Model):
        total_gen = 0
        for tdef in TECH_DEFS:
            name = tdef["name"]
            n = InputDir[tdef["numsites_key"]]
            Y = Y_vars[name]
            total_gen += sum(Y[i] * InputDir[tdef["energy_key"]][:, i].mean() * InputDir[tdef["power_key"]][i]
                             for i in range(n))
        
        TotalCurtailment = sum(Model.Delta[t] for t in range(InputDir["NumTimeSteps"])) / InputDir["NumTimeSteps"]
        return (total_gen - TotalCurtailment) * 24 * 365.25

    Model.OBJ = Objective(rule=objective_rule, sense=maximize)

    # =========================================================================
    # Per-site max turbine constraints — generic loop
    # =========================================================================
    for tdef in active_techs:
        name = tdef["name"]
        n = InputDir[tdef["numsites_key"]]
        Y = Y_vars[name]
        
        def _max_turb_rule(Model, i, _n=name, _tdef=tdef):
            return Y_vars[_n][i] <= InputDir[_tdef["maxnum_key"]][i]
        
        setattr(Model, f"Turbines_Cell_{name}",
                Constraint(range(n), rule=_max_turb_rule))

    # =========================================================================
    # Curtailment constraint — sum over all techs
    # =========================================================================
    def Curtailment_rule(Model, t):
        total_gen = 0
        for tdef in TECH_DEFS:
            name = tdef["name"]
            n = InputDir[tdef["numsites_key"]]
            Y = Y_vars[name]
            total_gen += sum(Y[i] * InputDir[tdef["energy_key"]][t, i] * InputDir[tdef["power_key"]][i]
                             for i in range(n))
        return -Model.Delta[t] + total_gen <= InputDir["RatedPowerMWTransmissionMW"]

    Model.Curtailment = Constraint(range(InputDir["NumTimeSteps"]), rule=Curtailment_rule)

    # =========================================================================
    # Collection system center selection — generic radious exclusion
    # =========================================================================
    Model.ChooseOneCircle = Constraint(expr=sum(Model.s[i] for i in range(InputDir["NumTransSites"])) == 1)

    IdxOut = {}
    for tdef in TECH_DEFS:
        name = tdef["name"]
        n = InputDir[tdef["numsites_key"]]
        if n > 0:
            IdxOut[name] = GetIdxOutRadious(InputDir["TransLatLong"], InputDir[tdef["latlong_key"]],
                                            InputDir["Max_CollectionRadious"])
        else:
            IdxOut[name] = [[] for _ in range(InputDir["NumTransSites"])]

    def MaximumRadious(Model, i):
        total = 0
        for tdef in TECH_DEFS:
            total += sum(Y_vars[tdef["name"]][j] for j in IdxOut[tdef["name"]][i])
        return total <= (1 - Model.s[i]) * BigM

    Model.Maximum_Radious = Constraint(range(InputDir["NumTransSites"]), rule=MaximumRadious)

    # =========================================================================
    # Design tracking and limits — generic loop
    # =========================================================================
    for tdef in active_techs:
        name = tdef["name"]
        nd = tdef["num_designs"]
        Y = Y_vars[name]
        W = W_vars[name]
        
        def _track_design_rule(Model, d, _name=name, _tdef=tdef):
            IdxVarPartOfDesign = np.where(InputDir[_tdef["design_key"]] == d)[0]
            return sum(Y_vars[_name][i] for i in IdxVarPartOfDesign) <= W_vars[_name][d] * BigM
        
        setattr(Model, f"TrackDesigns_{name}",
                Constraint(range(nd), rule=_track_design_rule))
        
        setattr(Model, f"LimitDesigns_{name}",
                Constraint(expr=sum(W[d] for d in range(nd)) == tdef["max_designs"]))
        
        n = InputDir[tdef["numsites_key"]]
        setattr(Model, f"SetLB_{name}",
                Constraint(expr=sum(Y[i] for i in range(n)) >= tdef["min_turbines"]))

    # =========================================================================
    # Overlap Constraints
    # =========================================================================
    # Physical co-location rules:
    #   - Wind occupies the air above the ocean surface (turbine + nacelle).
    #   - Wave devices (WECs) operate at/near the ocean surface.
    #   - Kites operate at depth in ocean currents.
    #
    # Co-location compatibility:
    #   - Wind + Wave:  CAN coexist (literature supports co-located farms;
    #                   WECs fit between wind platform moorings).
    #   - Wind + Kite:  CAN coexist (wind is airborne, kites are subsurface).
    #   - Wave + Kite:  CANNOT coexist (both occupy the water column at the
    #                   same site; they can be adjacent but not overlapping).
    #
    # Therefore we enforce:
    #   1. Self-overlaps for all techs (Wind-Wind, Wave-Wave, Kite-Kite) to
    #      prevent double-counting when multiple designs map to the same cell.
    #   2. Cross-tech overlap only for Wave <-> Kite.
    #
    # The max collection radius constraint already ensures all devices are
    # within the same general region for transmission purposes.
    # =========================================================================

    _empty_overlap = (np.empty((0, 2), dtype=int), np.empty(0),
                      np.empty((0, 2)), np.empty((0, 2)), np.empty(0))

    _tdef_lookup = {d["name"]: d for d in TECH_DEFS}

    # Define which overlap pairs to compute and enforce.
    # Each entry: (tech_A, tech_B, is_self, constraint_type)
    #   constraint_type: "self" = simple integer deduction
    #                    "cross" = area-weighted deduction
    OVERLAP_PAIRS = []

    # Self-overlaps for all active techs
    for tdef in active_techs:
        OVERLAP_PAIRS.append((tdef["name"], tdef["name"], True, "self"))

    # Cross-tech: Wave <-> Kite only
    if NumWaveDesigns > 0 and NumKiteDesigns > 0:
        OVERLAP_PAIRS.append(("Wave", "Kite", False, "cross"))
        OVERLAP_PAIRS.append(("Kite", "Wave", False, "cross"))

    # Compute overlaps for each defined pair
    overlaps = {}
    for a, b, is_self, ctype in OVERLAP_PAIRS:
        tdef_a = _tdef_lookup[a]
        tdef_b = _tdef_lookup[b]
        overlaps[(a, b)] = GetOverlaps_Idx_Area(
            InputDir[tdef_a["latlong_key"]], InputDir[tdef_a["reskm_key"]],
            InputDir[tdef_a["resdeg_key"]], InputDir[tdef_a["maxnum_key"]],
            InputDir[tdef_b["latlong_key"]], InputDir[tdef_b["reskm_key"]],
            InputDir[tdef_b["resdeg_key"]], InputDir[tdef_b["maxnum_key"]],
            SameTech=(1 if is_self else 0), PrintName=f"{a}-{b}")

    # Build overlap constraints per tech: for each tech A, gather all pairs
    # where A is the "reference" tech and build a single constraint set.
    for tdef_a in active_techs:
        a = tdef_a["name"]

        # Find all pairs where this tech is the reference (first element)
        relevant_pairs = [(a2, b2, s2, c2) for a2, b2, s2, c2 in OVERLAP_PAIRS if a2 == a]

        if len(relevant_pairs) == 0:
            continue

        # Collect unique site indices for tech A that have ANY overlap
        all_idx_arrays = [overlaps[(a2, b2)][0] for a2, b2, _, _ in relevant_pairs]
        nonempty = [arr for arr in all_idx_arrays if len(arr) > 0]

        if len(nonempty) == 0:
            continue

        combined = np.concatenate(nonempty)
        unique_idx = np.unique(combined[:, 0])

        # Pre-extract overlap data for this tech's pairs (avoids repeated lookups in rule)
        _pairs_data = []
        for a2, b2, is_self, ctype in relevant_pairs:
            _pairs_data.append({
                "b": b2, "is_self": is_self, "ctype": ctype,
                "idx_ov": overlaps[(a2, b2)][0],
                "area_ref": overlaps[(a2, b2)][2],
                "max_turb": overlaps[(a2, b2)][3],
                "pct_ov": overlaps[(a2, b2)][4],
            })

        def _overlap_rule(Model, i, _a=a, _pairs=_pairs_data):
            Y_a = Y_vars[_a]
            expr = Y_a[i] - InputDir[_tdef_lookup[_a]["maxnum_key"]][i]

            for pair in _pairs:
                idx_ov = pair["idx_ov"]
                if len(idx_ov) == 0:
                    continue

                mask = idx_ov[:, 0] == i
                j_indices = idx_ov[mask, 1]

                if len(j_indices) == 0:
                    continue

                Y_b = Y_vars[pair["b"]]

                if pair["ctype"] == "self":
                    # Self-overlap: simple integer deduction
                    expr -= sum(Y_b[j_indices[k]] for k in range(len(j_indices)))
                else:
                    # Cross-tech: area-weighted deduction
                    area_f = pair["area_ref"][mask]
                    mt_f = pair["max_turb"][mask]
                    pct_f = pair["pct_ov"][mask]
                    expr -= sum(
                        (area_f[k, 1] / mt_f[k, 1] * Y_b[j_indices[k]]) * pct_f[k]
                        * mt_f[k, 0] / area_f[k, 0]
                        for k in range(len(j_indices)))

            return expr <= 0

        setattr(Model, f"Overlap_{a}_ALL",
                Constraint(list(unique_idx), rule=_overlap_rule))

    ################################### Overlap Constraints ################################### End
    
    # #LCOE Target (Attached later on the LCOE iterator)
    # def LCOETarget(Model, LCOE_Max):  
    #     EGWind=sum(Model.Y_Wind[i]*InputDir["WindEnergy"][:,i].mean()*InputDir["RatedPowerWindTurbine"][i]  for i in range(InputDir["NumWindSites"])) #Energy generation from wind turbines [MW Avg]
    #     EGWave=sum(Model.Y_Wave[i]*InputDir["WaveEnergy"][:,i].mean()*InputDir["RatedPowerWaveTurbine"][i]  for i in range(InputDir["NumWaveSites"])) #Energy generation from wave turbines [MW Avg]
    #     EGKite=sum(Model.Y_Kite[i]*InputDir["KiteEnergy"][:,i].mean()*InputDir["RatedPowerKiteTurbine"][i]  for i in range(InputDir["NumKiteSites"])) #Energy generation from kite turbines [MW Avg]

    #     TotalCurtailment=sum(Model.Delta[t] for t in range(InputDir["NumTimeSteps"]))/InputDir["NumTimeSteps"] #Average curtailment MW

    #     MWhYear=(EGWind+EGWave+EGKite-TotalCurtailment)*24*365.25 # MWh Avg per year


    #     Cost_Wind=sum(Model.Y_Wind[i]*InputDir["AnnualizedCostWind"][i]  for i in range(InputDir["NumWindSites"]))
    #     Cost_Wave=sum(Model.Y_Wave[i]*InputDir["AnnualizedCostWave"][i]  for i in range(InputDir["NumWaveSites"]))
    #     Cost_Kite=sum(Model.Y_Kite[i]*InputDir["AnnualizedCostKite"][i]  for i in range(InputDir["NumKiteSites"]))
        
        
    #     Cost_Transmission=sum(Model.s[i]*InputDir["AnnualizedCostTransmission"][i] for i in Model.SiteTrs)
        
    #     TotalCost=Cost_Wind+Cost_Wave+Cost_Kite+Cost_Transmission
        

    #     return TotalCost<=LCOE_Max*MWhYear  

    return Model, InputDir


# ============================================================================
#  Helper functions for per-LCOE output generation
# ============================================================================

def _make_time_axis(TimeList):
    """Convert the TimeList from the model into matplotlib-compatible datetimes."""
    try:
        if isinstance(TimeList[0], (datetime,)):
            return list(TimeList)
        elif isinstance(TimeList[0], np.datetime64):
            return [t.astype('datetime64[ms]').astype(datetime) for t in TimeList]
        else:
            return [datetime.strptime(str(t), "%Y-%m-%d %H:%M:%S") for t in TimeList]
    except Exception:
        return list(np.arange(len(TimeList)))


def _compute_timeseries(InputDir, Optimal_Y_Wind, Optimal_Y_Wave, Optimal_Y_Kite, Optimal_Delta):
    """Compute full MW generation time series for each technology and curtailment."""
    T = InputDir["NumTimeSteps"]

    ts_wind = np.zeros(T)
    if InputDir["NumWindSites"] > 0 and InputDir["WindEnergy"].ndim == 2:
        for i in range(InputDir["NumWindSites"]):
            if Optimal_Y_Wind[i] > 0:
                ts_wind += Optimal_Y_Wind[i] * InputDir["WindEnergy"][:, i] * InputDir["RatedPowerWindTurbine"][i]

    ts_wave = np.zeros(T)
    if InputDir["NumWaveSites"] > 0 and InputDir["WaveEnergy"].ndim == 2:
        for i in range(InputDir["NumWaveSites"]):
            if Optimal_Y_Wave[i] > 0:
                ts_wave += Optimal_Y_Wave[i] * InputDir["WaveEnergy"][:, i] * InputDir["RatedPowerWaveTurbine"][i]

    ts_kite = np.zeros(T)
    if InputDir["NumKiteSites"] > 0 and InputDir["KiteEnergy"].ndim == 2:
        for i in range(InputDir["NumKiteSites"]):
            if Optimal_Y_Kite[i] > 0:
                ts_kite += Optimal_Y_Kite[i] * InputDir["KiteEnergy"][:, i] * InputDir["RatedPowerKiteTurbine"][i]

    ts_curtailment = np.array(Optimal_Delta)
    ts_total = ts_wind + ts_wave + ts_kite - ts_curtailment

    return ts_wind, ts_wave, ts_kite, ts_curtailment, ts_total


def _plot_total_generation(time_axis, ts_total, LCOETarget, CurrentLCOE, trans_capacity, save_path):
    """Plot total net generation vs. time."""
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(time_axis, ts_total, color='#2166ac', linewidth=0.4, alpha=0.85)
    ax.axhline(y=trans_capacity, color='red', linestyle='--', linewidth=1.0,
               label='Transmission Capacity (%.0f MW)' % trans_capacity)
    ax.set_xlabel('Time')
    ax.set_ylabel('Net Generation (MW)')
    ax.set_title('Total Net Generation - LCOE Target: %d $/MWh | Achieved: %.1f $/MWh' % (LCOETarget, CurrentLCOE))
    ax.legend(loc='upper right')
    ax.set_xlim(time_axis[0], time_axis[-1])
    ax.set_ylim(bottom=0)
    if isinstance(time_axis[0], datetime):
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def _plot_stacked_generation(time_axis, ts_wind, ts_wave, ts_kite, LCOETarget, CurrentLCOE, trans_capacity, save_path):
    """Stacked area plot of generation by technology."""
    fig, ax = plt.subplots(figsize=(14, 5))
    labels, series, colors = [], [], []
    if ts_wind.sum() > 0:
        labels.append('Wind'); series.append(ts_wind); colors.append('#4393c3')
    if ts_wave.sum() > 0:
        labels.append('Wave'); series.append(ts_wave); colors.append('#f4a582')
    if ts_kite.sum() > 0:
        labels.append('Kite'); series.append(ts_kite); colors.append('#92c5de')
    if len(series) > 0:
        ax.stackplot(time_axis, *series, labels=labels, colors=colors, alpha=0.85)
    ax.axhline(y=trans_capacity, color='red', linestyle='--', linewidth=1.0,
               label='Transmission Capacity (%.0f MW)' % trans_capacity)
    ax.set_xlabel('Time')
    ax.set_ylabel('Gross Generation (MW)')
    ax.set_title('Generation by Technology - LCOE Target: %d $/MWh | Achieved: %.1f $/MWh' % (LCOETarget, CurrentLCOE))
    ax.legend(loc='upper right')
    ax.set_xlim(time_axis[0], time_axis[-1])
    ax.set_ylim(bottom=0)
    if isinstance(time_axis[0], datetime):
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def _plot_curtailment(time_axis, ts_curtailment, LCOETarget, CurrentLCOE, save_path):
    """Plot curtailment vs. time."""
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.fill_between(time_axis, 0, ts_curtailment, color='#d6604d', alpha=0.7)
    ax.plot(time_axis, ts_curtailment, color='#b2182b', linewidth=0.4)
    ax.set_xlabel('Time')
    ax.set_ylabel('Curtailment (MW)')
    ax.set_title('Curtailment - LCOE Target: %d $/MWh | Achieved: %.1f $/MWh' % (LCOETarget, CurrentLCOE))
    ax.set_xlim(time_axis[0], time_axis[-1])
    ax.set_ylim(bottom=0)
    if isinstance(time_axis[0], datetime):
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def _plot_deployment_map(InputDir, Optimal_Y_Wind, Optimal_Y_Wave, Optimal_Y_Kite, Optimal_s,
                         LCOETarget, CurrentLCOE, total_units, save_path):
    """Plot site deployment map showing deployed turbines, transmission hub, and collection radius."""
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D

    TECH_COLORS = {"Wind": "dodgerblue", "Wave": "darkorange", "Kite": "limegreen"}

    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_facecolor("aliceblue")

    legend_handles = []
    all_lons = []
    all_lats = []
    n_total = 0

    tech_data = [
        ("Wind", Optimal_Y_Wind, InputDir["WindLatLong"]),
        ("Wave", Optimal_Y_Wave, InputDir["WaveLatLong"]),
        ("Kite", Optimal_Y_Kite, InputDir["KiteLatLong"]),
    ]

    for tech_name, Y_arr, LatLong in tech_data:
        if len(Y_arr) == 0 or len(LatLong) == 0:
            continue
        active = np.where(Y_arr > 0.5)[0]
        if len(active) == 0:
            continue
        ll = LatLong[active]
        units = Y_arr[active]
        color = TECH_COLORS.get(tech_name, "gray")
        sizes = 15 + units * 8
        ax.scatter(ll[:, 1], ll[:, 0], s=sizes, c=color,
                   edgecolors="black", linewidths=0.3, alpha=0.85, zorder=4)
        n_sites = len(units)
        n_units = int(units.sum())
        n_total += n_units
        legend_handles.append(
            Line2D([0], [0], marker="o", color="w", markerfacecolor=color,
                   markeredgecolor="black", markersize=8,
                   label="%s: %d sites, %d units" % (tech_name, n_sites, n_units)))
        all_lons.extend(ll[:, 1])
        all_lats.extend(ll[:, 0])

    # Transmission hub
    TransLatLong = InputDir["TransLatLong"]
    hub_idx = np.argmax(Optimal_s)
    hub_ll = TransLatLong[hub_idx]
    ax.scatter(hub_ll[1], hub_ll[0], s=250, c="red", marker="*",
              edgecolors="black", linewidths=0.8, zorder=6)
    legend_handles.append(
        Line2D([0], [0], marker="*", color="w", markerfacecolor="red",
               markeredgecolor="black", markersize=14, label="Transmission Hub"))
    all_lons.append(hub_ll[1])
    all_lats.append(hub_ll[0])

    # Collection radius
    r_km = InputDir["Max_CollectionRadious"]
    r_lat = r_km / 110.574
    r_lon = r_km / (111.32 * np.cos(np.radians(hub_ll[0])))
    circle = mpatches.Ellipse(
        (hub_ll[1], hub_ll[0]), width=2*r_lon, height=2*r_lat,
        fill=False, edgecolor="red", linewidth=1.5, linestyle="--", zorder=5)
    ax.add_patch(circle)
    legend_handles.append(
        Line2D([0], [0], color="red", linestyle="--", lw=1.5,
               label="Collection radius (%.0f km)" % r_km))

    PAD = 1.0
    if len(all_lons) > 0:
        ax.set_xlim(min(all_lons) - PAD, max(all_lons) + PAD)
        ax.set_ylim(min(all_lats) - PAD, max(all_lats) + PAD)

    ax.legend(handles=legend_handles, loc="upper left",
             frameon=True, framealpha=0.9, facecolor="white", title="Deployments")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Portfolio Deployment - LCOE Target: %d $/MWh | Achieved: %.1f $/MWh | %d total units"
                 % (LCOETarget, CurrentLCOE, n_total), fontsize=11)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def _plot_efficient_frontier(lcoe_targets, mw_avgs, save_path):
    """Efficient frontier: average generation (x) vs LCOE target (y)."""
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(mw_avgs, lcoe_targets, 'o-', color='#2166ac', markersize=8, linewidth=2)
    for x, y in zip(mw_avgs, lcoe_targets):
        ax.annotate("%.0f MW" % x, (x, y), textcoords="offset points",
                    xytext=(8, 4), fontsize=8, color='#333333')
    ax.set_xlabel("Average Net Generation (MW)")
    ax.set_ylabel("LCOE Target ($/MWh)")
    ax.set_title("Efficient Frontier: Generation vs LCOE Target")
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def _plot_stacked_costs(lcoe_targets, costs_wind, costs_wave, costs_kite, costs_trans, save_path):
    """Stacked bar chart of annualized costs by technology at each LCOE target."""
    fig, ax = plt.subplots(figsize=(8, 6))
    x = np.arange(len(lcoe_targets))
    width = 0.6
    labels_str = ["%d" % t for t in lcoe_targets]

    bottom = np.zeros(len(lcoe_targets))
    tech_items = [
        ("Wind", np.array(costs_wind), '#4393c3'),
        ("Wave", np.array(costs_wave), '#f4a582'),
        ("Kite", np.array(costs_kite), '#92c5de'),
        ("Transmission", np.array(costs_trans), '#d6604d'),
    ]
    for label, vals, color in tech_items:
        if vals.sum() > 0:
            ax.bar(x, vals, width, bottom=bottom, label=label, color=color)
            bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(labels_str)
    ax.set_xlabel("LCOE Target ($/MWh)")
    ax.set_ylabel("Annualized Cost (M$/year)")
    ax.set_title("Annualized System Cost Breakdown by Technology")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)


def _write_summary_csv(save_path, lcoe_targets, lcoe_achieved, mw_avgs,
                       mw_wind, mw_wave, mw_kite, mw_curtailment,
                       costs_wind, costs_wave, costs_kite, costs_trans):
    """Write a CSV summary table of all feasible LCOE solutions."""
    with open(save_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "LCOE_Target_$/MWh", "LCOE_Achieved_$/MWh",
            "Total_MW_Avg", "Wind_MW_Avg", "Wave_MW_Avg", "Kite_MW_Avg", "Curtailment_MW_Avg",
            "Cost_Wind_M$/yr", "Cost_Wave_M$/yr", "Cost_Kite_M$/yr",
            "Cost_Transmission_M$/yr", "Total_Cost_M$/yr"
        ])
        for i in range(len(lcoe_targets)):
            total_cost = costs_wind[i] + costs_wave[i] + costs_kite[i] + costs_trans[i]
            writer.writerow([
                lcoe_targets[i], "%.4f" % lcoe_achieved[i],
                "%.4f" % mw_avgs[i],
                "%.4f" % mw_wind[i], "%.4f" % mw_wave[i], "%.4f" % mw_kite[i],
                "%.4f" % mw_curtailment[i],
                "%.6f" % costs_wind[i], "%.6f" % costs_wave[i], "%.6f" % costs_kite[i],
                "%.6f" % costs_trans[i], "%.6f" % total_cost
            ])


def SolvePortOpt_MaxGen_LCOE_Iterator(PathWindDesigns, PathWaveDesigns, PathKiteDesigns, PathTransmissionDesign, LCOE_RANGE\
    ,Max_CollectionRadious,MaxDesignsWind, MaxDesingsWave, MaxDesingsKite,MinNumWindTurb,MinNumWaveTurb,MinNumKiteTrub\
    ,ReadMe,SavePath=None, PerLCOE_OutputFolder=None,
    WindTurbinesPerSite=4, WaveTurbinesPerSite=300, KiteTurbinesPerSite=390):

    #Create inputs and main model structure
    Model, InputDir=SolvePortOpt_MaxGen_Model(PathWindDesigns, PathWaveDesigns, PathKiteDesigns, PathTransmissionDesign, LCOE_RANGE\
        ,Max_CollectionRadious,MaxDesignsWind, MaxDesingsWave, MaxDesingsKite,MinNumWindTurb,MinNumWaveTurb,MinNumKiteTrub,
        WindTurbinesPerSite=WindTurbinesPerSite, WaveTurbinesPerSite=WaveTurbinesPerSite, KiteTurbinesPerSite=KiteTurbinesPerSite)

    opt = SolverFactory('gurobi', solver_io="python")
    opt.options['mipgap'] = 0.02

    #LCOE Target
    def LCOETarget_rule(Model, LCOE_Max):  
        EGWind=sum(Model.Y_Wind[i]*InputDir["WindEnergy"][:,i].mean()*InputDir["RatedPowerWindTurbine"][i]  for i in range(InputDir["NumWindSites"])) #Energy generation from wind turbines [MW Avg]
        EGWave=sum(Model.Y_Wave[i]*InputDir["WaveEnergy"][:,i].mean()*InputDir["RatedPowerWaveTurbine"][i]  for i in range(InputDir["NumWaveSites"])) #Energy generation from wave turbines [MW Avg]
        EGKite=sum(Model.Y_Kite[i]*InputDir["KiteEnergy"][:,i].mean()*InputDir["RatedPowerKiteTurbine"][i]  for i in range(InputDir["NumKiteSites"])) #Energy generation from kite turbines [MW Avg]

        TotalCurtailment=sum(Model.Delta[t] for t in range(InputDir["NumTimeSteps"]))/InputDir["NumTimeSteps"] #Average curtailment MW

        MWhYear=(EGWind+EGWave+EGKite-TotalCurtailment)*24*365.25 # MWh Avg per year


        Cost_Wind=sum(Model.Y_Wind[i]*InputDir["AnnualizedCostWind"][i]  for i in range(InputDir["NumWindSites"]))
        Cost_Wave=sum(Model.Y_Wave[i]*InputDir["AnnualizedCostWave"][i]  for i in range(InputDir["NumWaveSites"]))
        Cost_Kite=sum(Model.Y_Kite[i]*InputDir["AnnualizedCostKite"][i]  for i in range(InputDir["NumKiteSites"]))
        
        
        Cost_Transmission=sum(Model.s[i]*InputDir["AnnualizedCostTransmission"][i] for i in range(InputDir["NumTransSites"]))
        
        TotalCost=Cost_Wind+Cost_Wave+Cost_Kite+Cost_Transmission #M$
        TotalCost=TotalCost*10**6 #USD (Convert from M$ to USD)


        return TotalCost<=LCOE_Max*MWhYear  

    SaveFeasibility, Save_LCOETarget, Save_LCOE_Achieved, SaveTotalMWAvg = list(), list(), list(), list()
    Save_Y_Wind, Save_Y_Wave, Save_Y_Kite, Save_W_Wind, Save_W_Wave, Save_W_Kite, Save_s, Save_Delta = list(), list(), list(), list(), list(), list(), list(), list()
    Save_TotalMWAvgWind, Save_TotalMWAvgWave, Save_TotalMWAvgKite, Save_totalMWAvgCurtailment = list(), list(), list(), list()
    Save_CostWind, Save_CostWave, Save_CostKite, Save_CostTransmission = list(), list(), list(), list()

    LowestLCOE=10**10
    for LCOETarget in tqdm(InputDir["LCOE_RANGE"]):
        
        #Skip based on the algorithm progress, avoid repeating the same LCOE*
        if LCOETarget<LowestLCOE:    
            Bypass=0
            
            #Upperbound For the LCOE Activate Constraint
            LCOETarget_rule_tmp=LCOETarget_rule(Model,LCOETarget)
            Model.LCOE_Target = Constraint(rule=LCOETarget_rule_tmp)
            print("Running Model With LCOE= %.2f" % LCOETarget)
            
            try:
                results=opt.solve(Model, tee=True)
            except:
                Bypass=1
                Model.del_component(Model.LCOE_Target)  
        
            if Bypass==0:
                if (results.solver.status == SolverStatus.ok) and (results.solver.termination_condition == TerminationCondition.optimal):
                    SaveFeasibility.append(1)
                    Save_LCOETarget.append(LCOETarget)
                    
                    Optimal_Y_Wind=np.array([Model.Y_Wind[i].value for i in range(InputDir["NumWindSites"])])
                    Optimal_Y_Wave=np.array([Model.Y_Wave[i].value for i in range(InputDir["NumWaveSites"])])
                    Optimal_Y_Kite=np.array([Model.Y_Kite[i].value for i in range(InputDir["NumKiteSites"])])
                    Optimal_W_Wind=np.array([Model.W_Wind[i].value for i in range(len(Model.W_Wind))])
                    Optimal_W_Wave=np.array([Model.W_Wave[i].value for i in range(len(Model.W_Wave))])
                    Optimal_W_Kite=np.array([Model.W_Kite[i].value for i in range(len(Model.W_Kite))])
                    Optimal_s=np.array([Model.s[i].value for i in range(InputDir["NumTransSites"])])
                    Optimal_Delta=np.array([Model.Delta[i].value for i in range(InputDir["NumTimeSteps"])])
                    
                    Save_Y_Wind.append(Optimal_Y_Wind)
                    Save_Y_Wave.append(Optimal_Y_Wave)
                    Save_Y_Kite.append(Optimal_Y_Kite)
                    Save_W_Wind.append(Optimal_W_Wind)
                    Save_W_Wave.append(Optimal_W_Wave)
                    Save_W_Kite.append(Optimal_W_Kite)
                    Save_s.append(Optimal_s)
                    Save_Delta.append(Optimal_Delta)
                    

                    #Current LCOE
                    EGWind=sum(Optimal_Y_Wind[i]*InputDir["WindEnergy"][:,i].mean()*InputDir["RatedPowerWindTurbine"][i]  for i in range(InputDir["NumWindSites"])) #Energy generation from wind turbines [MW Avg]
                    EGWave=sum(Optimal_Y_Wave[i]*InputDir["WaveEnergy"][:,i].mean()*InputDir["RatedPowerWaveTurbine"][i]  for i in range(InputDir["NumWaveSites"])) #Energy generation from wave turbines [MW Avg]
                    EGKite=sum(Optimal_Y_Kite[i]*InputDir["KiteEnergy"][:,i].mean()*InputDir["RatedPowerKiteTurbine"][i]  for i in range(InputDir["NumKiteSites"])) #Energy generation from kite turbines [MW Avg]

                    TotalCurtailment=sum(Optimal_Delta[t] for t in range(InputDir["NumTimeSteps"]))/InputDir["NumTimeSteps"] #Average curtailment MW

                    MWhYear=(EGWind+EGWave+EGKite-TotalCurtailment)*24*365.25 # MWh Avg per year


                    Cost_Wind=sum(Optimal_Y_Wind[i]*InputDir["AnnualizedCostWind"][i]  for i in range(InputDir["NumWindSites"]))
                    Cost_Wave=sum(Optimal_Y_Wave[i]*InputDir["AnnualizedCostWave"][i]  for i in range(InputDir["NumWaveSites"]))
                    Cost_Kite=sum(Optimal_Y_Kite[i]*InputDir["AnnualizedCostKite"][i]  for i in range(InputDir["NumKiteSites"]))
                    
                    
                    Cost_Transmission=sum(Optimal_s[i]*InputDir["AnnualizedCostTransmission"][i] for i in range(InputDir["NumTransSites"]))
                    
                    TotalCost=Cost_Wind+Cost_Wave+Cost_Kite+Cost_Transmission #M$
                    TotalCost=TotalCost*10**6 #USD
                
                    CurrentLCOE=TotalCost/MWhYear
                    LowestLCOE=CurrentLCOE
                    
                    Save_LCOE_Achieved.append(CurrentLCOE)
                    SaveTotalMWAvg.append(MWhYear/(24*365.25))
                    Save_TotalMWAvgWind.append(EGWind)
                    Save_TotalMWAvgWave.append(EGWave)
                    Save_TotalMWAvgKite.append(EGKite)
                    Save_totalMWAvgCurtailment.append(TotalCurtailment)
                    Save_CostWind.append(Cost_Wind)
                    Save_CostWave.append(Cost_Wave)
                    Save_CostKite.append(Cost_Kite)
                    Save_CostTransmission.append(Cost_Transmission)
                    
                    
                    print("LCOE OPT: %.2f,\n MW Wind: %.2f,\nMW Wave: %.2f,\nMW Kite: %.2f,\nMW Curtailment: %.2f,\nMW Total: %.2f\n" % (CurrentLCOE,EGWind,EGWave,EGKite,TotalCurtailment,EGWind+EGWave+EGKite-TotalCurtailment))
                    
                    # === Per-LCOE output: save .npz, plots, and deployment map in subfolder ===
                    if PerLCOE_OutputFolder is not None:
                        lcoe_tag = "LCOE_%d" % int(LCOETarget)
                        lcoe_subfolder = os.path.join(PerLCOE_OutputFolder, lcoe_tag)
                        os.makedirs(lcoe_subfolder, exist_ok=True)
                        
                        # Compute full time series for this solution
                        ts_wind, ts_wave, ts_kite, ts_curtailment, ts_total = _compute_timeseries(
                            InputDir, Optimal_Y_Wind, Optimal_Y_Wave, Optimal_Y_Kite, Optimal_Delta)
                        
                        time_axis = _make_time_axis(InputDir["TimeList"])
                        trans_capacity = InputDir["RatedPowerMWTransmissionMW"]
                        
                        # Save per-LCOE .npz
                        npz_path = os.path.join(lcoe_subfolder, "Portfolio_%s.npz" % lcoe_tag)
                        np.savez(npz_path,
                            LCOE_Target=LCOETarget,
                            LCOE_Achieved=CurrentLCOE,
                            Total_MW_Avg=MWhYear/(24*365.25),
                            Wind_MW_Avg=EGWind,
                            Wave_MW_Avg=EGWave,
                            Kite_MW_Avg=EGKite,
                            Curtailment_MW_Avg=TotalCurtailment,
                            Cost_Wind_MperYear=Cost_Wind,
                            Cost_Wave_MperYear=Cost_Wave,
                            Cost_Kite_MperYear=Cost_Kite,
                            Cost_Transmission_MperYear=Cost_Transmission,
                            Total_Cost_MperYear=Cost_Wind+Cost_Wave+Cost_Kite+Cost_Transmission,
                            Y_Wind=Optimal_Y_Wind,
                            Y_Wave=Optimal_Y_Wave,
                            Y_Kite=Optimal_Y_Kite,
                            W_Wind=Optimal_W_Wind,
                            W_Wave=Optimal_W_Wave,
                            W_Kite=Optimal_W_Kite,
                            s_Transmission=Optimal_s,
                            Delta=Optimal_Delta,
                            TimeSeries_Wind_MW=ts_wind,
                            TimeSeries_Wave_MW=ts_wave,
                            TimeSeries_Kite_MW=ts_kite,
                            TimeSeries_Curtailment_MW=ts_curtailment,
                            TimeSeries_Total_MW=ts_total,
                            TimeList=InputDir["TimeList"],
                            Transmission_Capacity_MW=trans_capacity,
                        )
                        print("  Saved per-LCOE file: %s" % npz_path)
                        
                        # Generate time series plots
                        _plot_total_generation(time_axis, ts_total, LCOETarget, CurrentLCOE, trans_capacity,
                            os.path.join(lcoe_subfolder, "Plot_TotalGeneration.png"))
                        _plot_stacked_generation(time_axis, ts_wind, ts_wave, ts_kite, LCOETarget, CurrentLCOE, trans_capacity,
                            os.path.join(lcoe_subfolder, "Plot_StackedGenByTech.png"))
                        _plot_curtailment(time_axis, ts_curtailment, LCOETarget, CurrentLCOE,
                            os.path.join(lcoe_subfolder, "Plot_Curtailment.png"))
                        
                        # Generate deployment map
                        _plot_deployment_map(InputDir, Optimal_Y_Wind, Optimal_Y_Wave, Optimal_Y_Kite, Optimal_s,
                            LCOETarget, CurrentLCOE, int(Optimal_Y_Wind.sum()+Optimal_Y_Wave.sum()+Optimal_Y_Kite.sum()),
                            os.path.join(lcoe_subfolder, "Plot_DeploymentMap.png"))
                        
                        print("  Saved all outputs for %s" % lcoe_tag)
                    # === End per-LCOE output ===
                    
                    #Delete constraint for its modification in the next step of the for loop
                    Model.del_component(Model.LCOE_Target)

                else:# Something else is wrong
                    Model.del_component(Model.LCOE_Target)
                    SaveFeasibility.append(0)
                    Save_LCOETarget.append(None)
                    Save_LCOE_Achieved.append(None)
                    SaveTotalMWAvg.append(None)   
                    
                    Save_Y_Wind.append(None)
                    Save_Y_Wave.append(None)
                    Save_Y_Kite.append(None)
                    Save_W_Wind.append(None)
                    Save_W_Wave.append(None)
                    Save_W_Kite.append(None)
                    Save_s.append(None)
                    Save_Delta.append(None)
                    Save_TotalMWAvgWind.append(None)
                    Save_TotalMWAvgWave.append(None)
                    Save_TotalMWAvgKite.append(None)
                    Save_totalMWAvgCurtailment.append(None)
                    break

    #Save Results
    if SavePath!=None:
        np.savez(SavePath, 
                ReadMe=ReadMe,
                #Model Inputs
                PathWindDesigns=PathWindDesigns,
                PathWaveDesigns=PathWaveDesigns,
                PathKiteDesigns=PathKiteDesigns,
                PathTransmissionDesign=PathTransmissionDesign,
                LCOE_RANGE=LCOE_RANGE,
                Max_CollectionRadious=Max_CollectionRadious,
                MaxDesignsWind=MaxDesignsWind,
                MaxDesingsWave=MaxDesingsWave,
                MaxDesingsKite=MaxDesingsKite,
                MinNumWindTurb=MinNumWindTurb,
                MinNumWaveTurb=MinNumWaveTurb,
                MinNumKiteTrub=MinNumKiteTrub,

                #Model Outputs
                SaveFeasibility=SaveFeasibility,
                Save_LCOETarget=Save_LCOETarget,
                Save_LCOE_Achieved=Save_LCOE_Achieved,
                SaveTotalMWAvg=SaveTotalMWAvg,
                Save_TotalMWAvgWind=Save_TotalMWAvgWind,
                Save_TotalMWAvgWave=Save_TotalMWAvgWave,
                Save_TotalMWAvgKite=Save_TotalMWAvgKite,
                Save_totalMWAvgCurtailment=Save_totalMWAvgCurtailment,
                
                Save_Y_Wind=Save_Y_Wind,
                Save_Y_Wave=Save_Y_Wave,
                Save_Y_Kite=Save_Y_Kite,
                Save_W_Wind=Save_W_Wind,
                Save_W_Wave=Save_W_Wave,
                Save_W_Kite=Save_W_Kite,
                Save_s=Save_s,
                Save_Delta=Save_Delta,
                )

    # === Run-level summary outputs (CSV, efficient frontier, stacked costs) ===
    if PerLCOE_OutputFolder is not None:
        os.makedirs(PerLCOE_OutputFolder, exist_ok=True)

        # Save combined .npz into the main run folder
        combined_path = os.path.join(PerLCOE_OutputFolder, "Combined_AllLCOE.npz")
        np.savez(combined_path,
                ReadMe=ReadMe,
                PathWindDesigns=PathWindDesigns,
                PathWaveDesigns=PathWaveDesigns,
                PathKiteDesigns=PathKiteDesigns,
                PathTransmissionDesign=PathTransmissionDesign,
                LCOE_RANGE=LCOE_RANGE,
                Max_CollectionRadious=Max_CollectionRadious,
                MaxDesignsWind=MaxDesignsWind,
                MaxDesingsWave=MaxDesingsWave,
                MaxDesingsKite=MaxDesingsKite,
                MinNumWindTurb=MinNumWindTurb,
                MinNumWaveTurb=MinNumWaveTurb,
                MinNumKiteTrub=MinNumKiteTrub,
                SaveFeasibility=SaveFeasibility,
                Save_LCOETarget=Save_LCOETarget,
                Save_LCOE_Achieved=Save_LCOE_Achieved,
                SaveTotalMWAvg=SaveTotalMWAvg,
                Save_TotalMWAvgWind=Save_TotalMWAvgWind,
                Save_TotalMWAvgWave=Save_TotalMWAvgWave,
                Save_TotalMWAvgKite=Save_TotalMWAvgKite,
                Save_totalMWAvgCurtailment=Save_totalMWAvgCurtailment,
                Save_CostWind=Save_CostWind,
                Save_CostWave=Save_CostWave,
                Save_CostKite=Save_CostKite,
                Save_CostTransmission=Save_CostTransmission,
                Save_Y_Wind=Save_Y_Wind,
                Save_Y_Wave=Save_Y_Wave,
                Save_Y_Kite=Save_Y_Kite,
                Save_W_Wind=Save_W_Wind,
                Save_W_Wave=Save_W_Wave,
                Save_W_Kite=Save_W_Kite,
                Save_s=Save_s,
                Save_Delta=Save_Delta,
                )
        print("Saved combined results: %s" % combined_path)

        # Filter to feasible solutions only for summary plots
        feas_idx = [i for i, f in enumerate(SaveFeasibility) if f == 1]
        if len(feas_idx) > 0:
            f_lcoe_target = [Save_LCOETarget[i] for i in feas_idx]
            f_lcoe_achieved = [Save_LCOE_Achieved[i] for i in feas_idx]
            f_mw_avg = [SaveTotalMWAvg[i] for i in feas_idx]
            f_mw_wind = [Save_TotalMWAvgWind[i] for i in feas_idx]
            f_mw_wave = [Save_TotalMWAvgWave[i] for i in feas_idx]
            f_mw_kite = [Save_TotalMWAvgKite[i] for i in feas_idx]
            f_mw_curt = [Save_totalMWAvgCurtailment[i] for i in feas_idx]
            f_cost_wind = [Save_CostWind[i] for i in feas_idx]
            f_cost_wave = [Save_CostWave[i] for i in feas_idx]
            f_cost_kite = [Save_CostKite[i] for i in feas_idx]
            f_cost_trans = [Save_CostTransmission[i] for i in feas_idx]

            # Reverse order so lowest LCOE comes first (more intuitive for plots/CSV)
            f_lcoe_target = f_lcoe_target[::-1]
            f_lcoe_achieved = f_lcoe_achieved[::-1]
            f_mw_avg = f_mw_avg[::-1]
            f_mw_wind = f_mw_wind[::-1]
            f_mw_wave = f_mw_wave[::-1]
            f_mw_kite = f_mw_kite[::-1]
            f_mw_curt = f_mw_curt[::-1]
            f_cost_wind = f_cost_wind[::-1]
            f_cost_wave = f_cost_wave[::-1]
            f_cost_kite = f_cost_kite[::-1]
            f_cost_trans = f_cost_trans[::-1]

            # CSV summary
            _write_summary_csv(
                os.path.join(PerLCOE_OutputFolder, "Summary.csv"),
                f_lcoe_target, f_lcoe_achieved, f_mw_avg,
                f_mw_wind, f_mw_wave, f_mw_kite, f_mw_curt,
                f_cost_wind, f_cost_wave, f_cost_kite, f_cost_trans)
            print("Saved Summary.csv")

            # Efficient frontier plot
            _plot_efficient_frontier(f_lcoe_target, f_mw_avg,
                os.path.join(PerLCOE_OutputFolder, "Plot_EfficientFrontier.png"))
            print("Saved Plot_EfficientFrontier.png")

            # Stacked cost plot
            _plot_stacked_costs(f_lcoe_target, f_cost_wind, f_cost_wave, f_cost_kite, f_cost_trans,
                os.path.join(PerLCOE_OutputFolder, "Plot_StackedCosts.png"))
            print("Saved Plot_StackedCosts.png")
    # === End run-level summary outputs ===