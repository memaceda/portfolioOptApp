#Tools to manipulate wind turbine data - East Coast
#geo_env
import csv
import numpy as np
import xarray as xr
import pandas as pd
from datetime import datetime, timedelta
from GeneralGeoTools_EastCoast import GetDepth, GetDistanceToShore, GetTimeList, MinDistanceSetPoints
from tqdm import tqdm


#Read wind turbine data
def GetTurbineData(InputDataPath, WindTurbine):
    
    PowerCurve=[]
    PowerCurve.append(['0','0'])
    
    File_Wind=open(WindTurbine+'.txt', "r")
    File_Wind_csv=csv.reader(File_Wind,delimiter=';')
    
    for EachLine in File_Wind_csv:
        
        if File_Wind_csv.line_num==1:
            HubHeight=float(EachLine[1])
            
        if File_Wind_csv.line_num==2:
            Total_Efficiency=1-float(EachLine[1])
            
        if File_Wind_csv.line_num==3:
            RotorDiameter=float(EachLine[1])

        if File_Wind_csv.line_num==4:
            RatedPower=float(EachLine[1])
            
        if File_Wind_csv.line_num>=6:
            PowerCurve.append(EachLine[:])

    PowerCurve=np.asarray(PowerCurve, dtype='float32')
    
    File_Wind.close()
    
    return HubHeight, Total_Efficiency, RotorDiameter, PowerCurve, RatedPower


def FilterOnDepthShoreDistance(Depth, DistanceShore, DepthMinMax, DistanceShoreMinMax):
    IdxIn=(DistanceShore>=DistanceShoreMinMax[0]) * (DistanceShore<=DistanceShoreMinMax[1]) * (Depth>=DepthMinMax[0]) * (Depth<=DepthMinMax[1])
    
    return IdxIn

#Convert wind speed to energy in pu
def WindToEnergy(InputDataPath, WindTurbine, WindDataFile, WindSpeedHeightsAvailable, ResolutionKm=2, TimeDeltaHours=1, SavePath=None):
    """Convert wind speed data to energy output in per-unit.
    
    InputDataPath: Base path for input data
    WindTurbine: Name of the wind turbine specification file
    WindDataFile: Filename of the single wind data file (e.g. 'EastCoast_windspeed.npz')
                  Expected keys: 'time_index', 'coordinates', 'windspeed_100m', etc.
    WindSpeedHeightsAvailable: Dict mapping height (int) to key name in the wind data file
                               e.g. {100: 'windspeed_100m', 140: 'windspeed_140m', ...}
    ResolutionKm: Spatial resolution in km
    TimeDeltaHours: Time step in hours (used if time_index cannot be auto-detected)
    SavePath: Path to save output .npz file (None = don't save)
    """
       
    HubHeight, Total_Efficiency, RotorDiameter, PowerCurve, RatedPower=GetTurbineData(InputDataPath, WindTurbine)

    HeightsAvailable=np.asarray(list(WindSpeedHeightsAvailable.keys()),dtype="int")

    #Get the two heights bracketing the hub height for wind shear interpolation
    #ul/uh=(zl/zh)^alpha

    IdxUpperWindFile=np.argmin(np.abs(HeightsAvailable-HubHeight)) #Get the closest height available
    if HeightsAvailable[IdxUpperWindFile]-HubHeight<0:
        IdxUpperWindFile=min(IdxUpperWindFile+1,len(HeightsAvailable)-1)

    IdxUpperWindFile=max(IdxUpperWindFile,1)
    IdxLowerWindFile=IdxUpperWindFile-1

    LWindKey=WindSpeedHeightsAvailable[list(WindSpeedHeightsAvailable.keys())[IdxLowerWindFile]]
    HWindKey=WindSpeedHeightsAvailable[list(WindSpeedHeightsAvailable.keys())[IdxUpperWindFile]]

    # Load from single wind data file
    WindData=np.load(WindDataFile, allow_pickle=True)
    LWindData=WindData[LWindKey]
    HWindData=WindData[HWindKey]
    
    # Get coordinates (new format: 'coordinates' with columns [lat, long])
    LatLong=WindData["coordinates"]
    
    # Get time information from file
    time_index=WindData["time_index"]
    StartDate=pd.Timestamp(time_index[0])
    EndDate=pd.Timestamp(time_index[-1])
    # Auto-detect time delta from first two timestamps
    if len(time_index) >= 2:
        TimeDeltaHours=int((pd.Timestamp(time_index[1]) - pd.Timestamp(time_index[0])).total_seconds() / 3600)
       
    Depth=GetDepth(InputDataPath, LatLong)
    DistanceShore=GetDistanceToShore(InputDataPath, LatLong)
    
    #Exclude points that are too shallow or too far from shore
    IdxIn=FilterOnDepthShoreDistance(Depth, DistanceShore, DepthMinMax=(3,1000), DistanceShoreMinMax=(3,100))
    LWindData=LWindData[:,IdxIn]
    HWindData=HWindData[:,IdxIn]
    LatLong=LatLong[IdxIn,:]
    Depth=Depth[IdxIn]
    DistanceShore=DistanceShore[IdxIn]
    
    
    # HubHeight
    LWindData[LWindData<0.01]=0.01 #To avoid log(0)
    HWindData[HWindData<0.01]=0.01 #To avoid log(0)
    alpha=np.log(HWindData/LWindData)/np.log(HeightsAvailable[IdxUpperWindFile]/HeightsAvailable[IdxLowerWindFile])
    alpha=np.median(alpha)
    
    if HeightsAvailable[IdxUpperWindFile]<=HubHeight:
        h_ref=HeightsAvailable[IdxUpperWindFile]
        WS_Ref=HWindData
    else:
        h_ref=HeightsAvailable[IdxLowerWindFile]
        WS_Ref=LWindData
    
    WS_Hub=WS_Ref*(HubHeight/h_ref)**alpha #Wind speed at the hub height

    WindEnergy_pu=np.interp(WS_Hub,PowerCurve[:,0],PowerCurve[:,1])

    ReadMe='\
    EnergyPu: pu wind energy \n\
    1) The data is in '+str(TimeDeltaHours)+'h discretization starting at '+str(StartDate)+' and going up to '\
     +str(EndDate)
    
    RatedPower=RatedPower
    TimeList=GetTimeList(StartDate, EndDate, TimeDeltaHours=TimeDeltaHours)
    
    if SavePath!=None:
        np.savez(SavePath, ReadMe=ReadMe, Energy_pu=WindEnergy_pu.astype(np.float16), RatedPower=RatedPower, LatLong=LatLong.astype(np.float32), Depth=Depth,\
            DistanceShore=DistanceShore.astype(np.float32),RawResource=WS_Hub.astype(np.float16),TimeList=TimeList,ResolutionKm=ResolutionKm )
        

    return WindEnergy_pu, RatedPower, LatLong, WS_Hub, Depth, DistanceShore, TimeList, ResolutionKm

def GetCostAndGenerationWindTurbine(InputDataPath, WindCostPath, WindTurbine, WindDataFile, WindSpeedHeightsAvailable, TurbinePath=None, SavePath=None):

    if TurbinePath is None:
        TurbinePath = WindTurbine
    WindEnergy_pu, RatedPower, LatLong, WS_Hub, Depth, DistanceShore, TimeList, ResolutionKm=WindToEnergy(InputDataPath, TurbinePath, WindDataFile, WindSpeedHeightsAvailable, ResolutionKm=2, SavePath=None)   
    #Read EXCEL data and get NREL information
    CAPEX=pd.read_excel(WindCostPath,sheet_name="CAPEX")
    OPEX=pd.read_excel(WindCostPath,sheet_name="OPEX")

    ATB_SiteToLandfall=CAPEX["SiteToLandfall"]
    ATB_AvgDepth=CAPEX["AvgDepth"]
    ATB_TRG=CAPEX["TRG"]

    CAPEX=CAPEX[WindTurbine]
    OPEX=OPEX[WindTurbine]

    CAPEX=CAPEX*RatedPower*(10**-3) #[$/Year]
    OPEX =OPEX*RatedPower*(10**-3) #[$/Year]

    FCR=6.8/100 # Factor of Capital Return(WECC ATB-2023)
    IdxIn=Depth<=np.max(ATB_AvgDepth)*1.1 #Maxmimum depth which we have cost estimates
            
    #Filter for the region where we have cost estimated
    WindEnergy_pu=WindEnergy_pu[:,IdxIn]
    LatLong=LatLong[IdxIn,:]
    WS_Hub=WS_Hub[:,IdxIn]
    Depth=Depth[IdxIn] 
    DistanceShore=DistanceShore[IdxIn]


    Diff_Depth=np.reshape(Depth,(len(Depth),1))-np.reshape(ATB_AvgDepth,(1,len(ATB_AvgDepth)))
    Diff_Distance=np.reshape(DistanceShore,(len(DistanceShore),1))-np.reshape(ATB_SiteToLandfall,(1,len(ATB_SiteToLandfall)))

    EuclidianDistance=(Diff_Depth**2+Diff_Distance**2)
    Idx_NRELTurbine=np.argmin(EuclidianDistance,axis=1)

    TRG_site=ATB_TRG[Idx_NRELTurbine]
    CAPEX_site=CAPEX[Idx_NRELTurbine]
    OPEX_site=OPEX[Idx_NRELTurbine]

    AnnualizedCost=CAPEX_site*FCR + OPEX_site

    ReadMe='\
    EnergyPu: pu wind energy \n\
    1) The data starts at '+str(TimeList[0])+' and goes up to '\
        +str(TimeList[-1])+'\n \
    2) Cost Values in M$, energy values in MW'
    
    # TimeList already computed in WindToEnergy and returned above
    
    AnnualizedCost=AnnualizedCost/(10**6)
    CAPEX_site=CAPEX_site/(10**6)
    OPEX_site=OPEX_site/(10**6)
    RatedPower=RatedPower/(10**6)
    NumberOfCellsPerSite=np.ones(LatLong.shape[0]) #one site per cell

    if SavePath!=None:
        np.savez(SavePath, ReadMe=ReadMe, Energy_pu=WindEnergy_pu.astype(np.float16), RatedPower=RatedPower, LatLong=LatLong.astype(np.float32), Depth=Depth,\
            DistanceShore=DistanceShore.astype(np.float16), TRG_site=TRG_site, CAPEX_site=CAPEX_site.astype(np.float16), OPEX_site=OPEX_site.astype(np.float16),\
                AnnualizedCost=AnnualizedCost.astype(np.float16), RawResource=WS_Hub.astype(np.float16), TimeList=TimeList, NumberOfCellsPerSite=NumberOfCellsPerSite,
                ResolutionKm=ResolutionKm, ResolutionDegrees=-1)
        
    return WindEnergy_pu, RatedPower, LatLong, WS_Hub, Depth, DistanceShore, TRG_site, CAPEX_site, OPEX_site, AnnualizedCost, TimeList, NumberOfCellsPerSite


# Filter for WTK-NREL sites   
def FilterForWTKDataset(ReferenceDataPath, WTKPath, SavePath=None):
    Data=np.load(ReferenceDataPath,allow_pickle=True)

    Energy_Pu=Data["Energy_pu"]
    RawResource=Data["RawResource"]
    RatedPower=Data["RatedPower"]
    NumberOfCellsPerSite=Data["NumberOfCellsPerSite"]

    TimeList=Data["TimeList"]
    LatLong=Data["LatLong"]
    Depth=Data["Depth"]
    DistanceShore=Data["DistanceShore"]
    CAPEX_site=Data["CAPEX_site"]
    OPEX_site=Data["OPEX_site"]
    AnnualizedCost=Data["AnnualizedCost"]
    ResolutionDegrees=Data["ResolutionDegrees"]
    ResolutionKm=Data["ResolutionKm"]
    


    #def FilterUsingWTKSites(WTKPath):  
    NRELLimitSites=pd.read_csv(WTKPath)
    NREL_Lat=NRELLimitSites["latitude"].values
    NREL_Long=NRELLimitSites["longitude"].values
    fraction_of_usable_area=NRELLimitSites["fraction_of_usable_area"].values
    power_curve= NRELLimitSites["power_curve"].values


    MaxLat=np.max(LatLong[:,0])
    MinLat=np.min(LatLong[:,0])
    MaxLong=np.max(LatLong[:,1])
    MinLong=np.min(LatLong[:,1])

    IdxNRELFilter=(NREL_Lat<=MaxLat) & (NREL_Lat>=MinLat) & (NREL_Long<=MaxLong) & (NREL_Long>=MinLong)\
        & (fraction_of_usable_area==1) &(power_curve=="offshore")

    NREL_Lat=NREL_Lat[IdxNRELFilter]
    NREL_Long=NREL_Long[IdxNRELFilter]
    NREL_LatLong=np.stack((NREL_Lat, NREL_Long),axis=1)

    IdxMin, DMin=MinDistanceSetPoints(LatLong, NREL_LatLong)
    IdxMin=IdxMin[DMin<=3]# Keep all the points that distance less than 3km from a NREL site


    Energy_Pu=Energy_Pu[:,IdxMin]
    RawResource=RawResource[:,IdxMin]

    LatLong=LatLong[IdxMin,:]
    Depth=Depth[IdxMin]
    DistanceShore=DistanceShore[IdxMin]
    CAPEX_site=CAPEX_site[IdxMin]
    OPEX_site=OPEX_site[IdxMin]
    AnnualizedCost=AnnualizedCost[IdxMin]

    DataDir={"Energy_pu":Energy_Pu,
            "RawResource":RawResource,
            "TimeList":TimeList,
            "LatLong":LatLong,
            "Depth":Depth,
            "DistanceShore":DistanceShore,
            "CAPEX_site":CAPEX_site,
            "OPEX_site":OPEX_site,
            "AnnualizedCost":AnnualizedCost}
    
    if SavePath!=None:
        np.savez(SavePath,  Energy_pu=Energy_Pu.astype(np.float16), RatedPower=RatedPower, LatLong=LatLong.astype(np.float32), Depth=Depth,\
            DistanceShore=DistanceShore.astype(np.float16), CAPEX_site=CAPEX_site.astype(np.float16), OPEX_site=OPEX_site.astype(np.float16),\
                AnnualizedCost=AnnualizedCost.astype(np.float16), RawResource=RawResource.astype(np.float16), TimeList=TimeList, NumberOfCellsPerSite=NumberOfCellsPerSite,
                ResolutionDegrees=ResolutionDegrees, ResolutionKm=ResolutionKm)
    
    return DataDir
