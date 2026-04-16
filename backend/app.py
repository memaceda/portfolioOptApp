#env Gurobi

from flask import Flask, jsonify, send_file, request
from flask_cors import CORS, cross_origin

import csv
import numpy as np
import xarray as xr
import sys
import json
from datetime import datetime, timedelta
from tqdm import tqdm
import time
import os
import io
import shutil
from PIL import Image
from pathlib import Path
import traceback

from Port_Opt_MaxGeneration_EastCoast import SolvePortOpt_MaxGen_LCOE_Iterator
from GeneralGeoTools_EastCoast import PlotEfficientFrontier, ChangeTimeSpaceResolution
from gurobipy import *

app = Flask(__name__)
CORS(app)

path = Path(__file__).parent

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
# East Coast input data
GEOSPATIAL_DATA = str(path / "Geospatial Data")
TECH_DESIGNS = str(path / "Tech Designs")
RESOURCE_DATA = str(path / "Resource Data")

# Generated outputs (kept for frontend backward-compat)
OUTPUT_DATA = str(path / "OutputData")
INPUT_DATA = str(path / "InputData")
PORTFOLIOS_DIR = os.path.join(OUTPUT_DATA, "Portfolios")
PLOTS_DIR = os.path.join(OUTPUT_DATA, "Plots", "Portfolios")

os.makedirs(PORTFOLIOS_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DATA, "Wind"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DATA, "Wave"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DATA, "OceanCurrent"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DATA, "Transmission"), exist_ok=True)


@app.route('/test', methods=['GET', 'POST'])
def test():
    return jsonify({'message': 'The server is running'})


@app.route('/resourceUpload', methods=['POST'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def resourceUpload():
    try:
        data = request.get_json()
        print(f"Received data: {data}")
    except Exception as e:
        print(f"JSON parse error: {str(e)}")

    try:
        from werkzeug.utils import secure_filename
        files = request.files.getlist('files')
        print(files)
        saved_files = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                if "PowerTimeSeriesKite" in filename:
                    save_dir = os.path.join(OUTPUT_DATA, 'OceanCurrent')
                    os.makedirs(save_dir, exist_ok=True)
                    print(f"Saving to {os.path.join(save_dir, filename)}")
                    file.save(os.path.join(save_dir, filename))
                saved_files.append(filename)

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    return jsonify({'message': f'{len(saved_files)} file(s) uploaded successfully', 'files': saved_files}), 200


@app.route('/generateWindBinaries', methods=['GET', 'POST'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def generate_wind_binaries():
    try:
        data = request.get_json()
        print(f"Received data: {data}")
    except Exception as e:
        print(f"JSON parse error: {str(e)}")

    required_fields = ['WindTurbine', 'ResolutionKm']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    try:
        requestdata = request.get_json()
        WindTurbine = requestdata['WindTurbine']
        ResolutionKm = requestdata['ResolutionKm']

        from WindTurbineTools_EastCoast import GetCostAndGenerationWindTurbine

        WindCostPath = os.path.join(INPUT_DATA, "Wind", "CostWindTurbines.xlsx")
        WindDataDir = os.path.join(INPUT_DATA, "Wind")

        WindSpeedHeightsAvailable = {
            100: "windspeed_100m",
            140: "windspeed_140m",
            160: "windspeed_160m",
        }

        for tb in WindTurbine:
            TurbinePath = os.path.join(INPUT_DATA, "Wind", tb)
            WindDataFile = os.path.join(WindDataDir, "EastCoast_windspeed.npz")
            SavePath = os.path.join(OUTPUT_DATA, "Wind", f"GenCost_{tb}.npz")

            if not os.path.exists(SavePath):
                GetCostAndGenerationWindTurbine(
                    WindDataDir, WindCostPath, WindTurbine=tb,
                    WindDataFile=WindDataFile,
                    WindSpeedHeightsAvailable=WindSpeedHeightsAvailable,
                    TurbinePath=TurbinePath,
                    SavePath=SavePath,
                )
            else:
                print(f"{SavePath} already exists")

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    return jsonify({'message': 'The server executed this API call.'})


@app.route('/windInputGeneration', methods=['POST'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def windInputGeneration():
    try:
        data = request.get_json()
        print(f"Received data: {data}")
    except Exception as e:
        print(f"JSON parse error: {str(e)}")

    required_fields = ['wind', 'min_year', 'max_year']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    CurrentTimeResolution = 1
    NewTimeResolution = 3
    StepsPerDegree = 10

    try:
        requestdata = request.get_json()
        min_year = requestdata['min_year']
        max_year = requestdata['max_year']
        winds = requestdata['wind']
        StartDateTime = datetime(min_year, 1, 1, 0, 0)
        EndDateTime = datetime(max_year, 12, 31, 23)

        winds = ["GenCost" + wind.split("GenCost")[-1].split(".")[0] for wind in winds]

        file_list = winds
        for file in file_list:
            ReferenceDataPath = os.path.join(OUTPUT_DATA, "Wind", file + ".npz")
            NewSavePath = os.path.join(
                OUTPUT_DATA, "Wind",
                f"Upscale3h_0.1Degree_{min_year}_{max_year}_{file}.npz"
            )
            if not os.path.exists(NewSavePath):
                ChangeTimeSpaceResolution(
                    ReferenceDataPath, CurrentTimeResolution, NewTimeResolution,
                    StepsPerDegree, StartDateTime, EndDateTime,
                    NewSavePath=NewSavePath
                )
            else:
                print(f"{NewSavePath} already exists")

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    return jsonify({'message': 'The server executed this API call.'})


def merge_kite_years(min_year, max_year, BCS):
    """Merge range of years for each kite design."""
    import datetime as dt
    years = range(min_year, max_year)
    VerticalDepth = [50, 100, 150, 200]
    i_vd = 0

    output_path = os.path.join(
        OUTPUT_DATA, 'OceanCurrent',
        f'PowerTimeSeriesKite_VD{VerticalDepth[i_vd]}_BCS{BCS}_{min_year}_{max_year}.npz'
    )
    if os.path.exists(output_path):
        print(f"{output_path} already exists, skipping merge.")
        return

    for year in tqdm(years):
        SavePowerTimeSeriesPath = os.path.join(OUTPUT_DATA, 'OceanCurrent', f'{year}_')
        PathKiteParams = SavePowerTimeSeriesPath + f'PowerTimeSeriesKite_VD{VerticalDepth[i_vd]}_BCS{BCS}.npz'
        Data = np.load(PathKiteParams, allow_pickle=True)

        Energy_pu = Data['Energy_pu']
        RawResource = Data['RawResource']
        TimeList = Data['TimeList']
        LatLong = Data['LatLong']
        Depth = Data['Depth']
        DistanceShore = Data['DistanceShore']
        CAPEX_site = Data['CAPEX_site']
        OPEX_site = Data['OPEX_site']
        AnnualizedCost = Data['AnnualizedCost']
        NumberOfCellsPerSite = Data['NumberOfCellsPerSite']
        RatedPower = Data['RatedPower']
        ResolutionDegrees = Data['ResolutionDegrees']
        ResolutionKm = Data['ResolutionKm']
        MatlabSiteIdx = Data['MatlabSiteIdx']
        StructuralMass = Data['StructuralMass']
        Span = Data['Span']
        AspectRatio = Data['AspectRatio']
        Length = Data['Length']
        Diameter = Data['Diameter']

        if year == np.min(years):
            Energy_pu_all = Energy_pu
            RawResource_all = RawResource
            TimeList_all = TimeList
            LatLong_all = LatLong
            Depth_all = Depth
            DistanceShore_all = DistanceShore
            CAPEX_site_all = CAPEX_site
            OPEX_site_all = OPEX_site
            AnnualizedCost_all = AnnualizedCost
            NumberOfCellsPerSite_all = NumberOfCellsPerSite
            RatedPower_all = RatedPower
            ResolutionDegrees_all = ResolutionDegrees
            ResolutionKm_all = ResolutionKm
            MatlabSiteIdx_all = MatlabSiteIdx
            StructuralMass_all = StructuralMass
            Span_all = Span
            AspectRatio_all = AspectRatio
            Length_all = Length
            Diameter_all = Diameter
        else:
            IdxSpecific = []
            for i in range(len(LatLong_all)):
                matches = np.where(
                    (LatLong[:, 0] == LatLong_all[i, 0]) &
                    (LatLong[:, 1] == LatLong_all[i, 1])
                )[0]
                if matches.size > 0:
                    IdxSpecific.append(matches[0])

            LatLong = LatLong[IdxSpecific, :]
            Energy_pu = Energy_pu[:, IdxSpecific]
            RawResource = RawResource[IdxSpecific]

            IdxAll = []
            for i in range(len(LatLong)):
                matches = np.where(
                    (LatLong_all[:, 0] == LatLong[i, 0]) &
                    (LatLong_all[:, 1] == LatLong[i, 1])
                )[0]
                if matches.size > 0:
                    IdxAll.append(matches[0])

            LatLong_all = LatLong_all[IdxAll, :]
            Depth_all = Depth_all[IdxAll]
            DistanceShore_all = DistanceShore_all[IdxAll]
            AnnualizedCost_all = AnnualizedCost_all[IdxAll]
            NumberOfCellsPerSite_all = NumberOfCellsPerSite_all[IdxAll]
            MatlabSiteIdx_all = MatlabSiteIdx_all[IdxAll]
            Energy_pu_all = Energy_pu_all[:, IdxAll]
            RawResource_all = RawResource_all[IdxAll]

            Energy_pu_all = np.concatenate((Energy_pu_all, Energy_pu), axis=0)
            RawResource_all = (RawResource + RawResource_all) / 2

        SavePowerTimeSeriesPath = os.path.join(OUTPUT_DATA, 'OceanCurrent', '')
        PathKiteParams = (
            SavePowerTimeSeriesPath +
            f'PowerTimeSeriesKite_VD{VerticalDepth[i_vd]}_BCS{BCS}_{min_year}_{max_year}.npz'
        )

        TimeList_all = [
            dt.datetime(2007, 1, 1, 0, 0) + dt.timedelta(hours=3 * i)
            for i in range(Energy_pu_all.shape[0])
        ]
        np.savez(
            PathKiteParams,
            Energy_pu=Energy_pu_all, RawResource=RawResource_all,
            TimeList=TimeList_all, LatLong=LatLong_all, Depth=Depth_all,
            DistanceShore=DistanceShore_all,
            CAPEX_site=CAPEX_site_all, OPEX_site=OPEX_site_all,
            AnnualizedCost=AnnualizedCost_all,
            NumberOfCellsPerSite=NumberOfCellsPerSite_all,
            RatedPower=RatedPower_all, ResolutionDegrees=ResolutionDegrees_all,
            ResolutionKm=ResolutionKm_all, MatlabSiteIdx=MatlabSiteIdx_all,
            StructuralMass=StructuralMass_all,
            Span=Span_all, AspectRatio=AspectRatio_all,
            Length=Length_all, Diameter=Diameter_all,
        )


@app.route('/kiteInputGeneration', methods=['POST'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def kiteInputGeneration():
    try:
        data = request.get_json()
        print(f"Received data: {data}")
    except Exception as e:
        print(f"JSON parse error: {str(e)}")

    required_fields = ['kite', 'min_year', 'max_year']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    try:
        requestdata = request.get_json()
        min_year = requestdata['min_year']
        max_year = requestdata['max_year']
        kites = requestdata['kite']
        i_vd = 0

        for kite in kites:
            st = kite
            VD = 0
            BCS = 0
            for it in st.split('_'):
                if 'VD' in it:
                    VD = int(it.split('VD')[-1])
                if 'BCS' in it:
                    BCS = float(it.split('BCS')[-1])

            if max_year == min_year:
                new_file = os.path.join(
                    OUTPUT_DATA, 'OceanCurrent',
                    f'PowerTimeSeriesKite_VD{VD}_BCS{BCS}_{min_year}_{max_year}.npz'
                )
                if os.path.exists(new_file):
                    print(f"'{new_file}' already exists (uploaded by user), skipping copy.")
                else:
                    source_file = os.path.join(
                        OUTPUT_DATA, 'OceanCurrent',
                        f'{min_year}_PowerTimeSeriesKite_VD{VD}_BCS{BCS}.npz'
                    )
                    shutil.copy2(source_file, new_file)
                    print(f"File '{source_file}' copied to '{new_file}'")
            else:
                for year in tqdm(range(min_year, max_year)):
                    StartDTime = datetime(year, 1, 1, 0, 0, 0)
                    EndDTime = datetime(year, 12, 31, 23, 0, 0)

                    SaveMatPath = os.path.join(INPUT_DATA, "OceanCurrent", "")
                    FullMatlabHycomDataPath = (
                        SaveMatPath + "OCSpeedHycom_" +
                        StartDTime.strftime("%Y%m%d") + "_" +
                        EndDTime.strftime("%Y%m%d") + ".mat"
                    )
                    SavePowerTimeSeriesPath = os.path.join(
                        OUTPUT_DATA, 'OceanCurrent', f'{year}_'
                    )

                    kite_file = SavePowerTimeSeriesPath + f'PowerTimeSeriesKite_VD{VD}_BCS{BCS}.npz'
                    if not os.path.isfile(kite_file):
                        print(f"Running year {year} VD {VD} BCS {BCS}")
                    else:
                        print(f"{kite_file} already exists")

                merge_kite_years(min_year, max_year, BCS)

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    return jsonify({'message': 'The server executed this API call.'})


@app.route('/waveInputGeneration', methods=['POST'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def waveInputGeneration():
    try:
        data = request.get_json()
        print(f"Received data: {data}")
    except Exception as e:
        print(f"JSON parse error: {str(e)}")

    required_fields = ['wave', 'min_year', 'max_year']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    try:
        requestdata = request.get_json()
        min_year = requestdata['min_year']
        max_year = requestdata['max_year']
        waves = requestdata['wave']

        for wave in waves:
            wave_output = os.path.join(OUTPUT_DATA, wave)
            if not os.path.exists(wave_output):
                wave_type = 'Pelamis' if 'Pelamis' in wave else 'RM3'
                source_wave_file = os.path.join(OUTPUT_DATA, 'Wave', f'2005_2019_{wave_type}.npz')
                with np.load(source_wave_file, allow_pickle=True) as data:
                    time_list = data['TimeList']
                    mask = np.array([min_year <= dt.year <= max_year for dt in time_list])

                    energy_pu = data['Energy_pu']
                    raw_resource = data['RawResource']

                    filtered_energy = energy_pu[mask, :]
                    filtered_resource = raw_resource[mask, :]
                    filtered_time = time_list[mask]

                    print("Filtered TimeList:", filtered_time)
                    print("Filtered TimeList Shape:", filtered_time.shape)
                    print("Filtered Energy_pu shape:", filtered_energy.shape)

                    np.savez(
                        wave_output,
                        Energy_pu=filtered_energy, RawResource=filtered_resource,
                        TimeList=filtered_time, LatLong=data["LatLong"],
                        Depth=data['Depth'], DistanceShore=data['DistanceShore'],
                        CAPEX_site=data['CAPEX_site'], OPEX_site=data['OPEX_site'],
                        AnnualizedCost=data['AnnualizedCost'],
                        NumberOfCellsPerSite=data['NumberOfCellsPerSite'],
                        RatedPower=data['RatedPower'],
                        ResolutionDegrees=data['ResolutionDegrees'],
                        ResolutionKm=data['ResolutionKm'], LCOE=data['LCOE'],
                    )
            else:
                print(f"{wave_output} already exists")

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    return jsonify({'message': 'The server executed this API call.'})


@app.route('/portfolioOptimization', methods=['POST'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def portfolioOptimization():
    try:
        data = request.get_json()
        print(f"Received data: {data}")
    except Exception as e:
        print(f"JSON parse error: {str(e)}")

    required_fields = ['wind', 'wave', 'kite', 'transmission']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    PathWindDesigns = []
    PathKiteDesigns = []
    PathWaveDesigns = []
    PathCoaxialDesigns = []
    PathTransmissionDesign = []
    GeneralPathResources = os.path.join(OUTPUT_DATA, "")

    try:
        requestdata = request.get_json()

        winds = requestdata['wind']
        for wind in winds:
            PathWindDesigns.append(GeneralPathResources + wind)

        kites = requestdata['kite']
        for kite in kites:
            PathKiteDesigns.append(GeneralPathResources + kite)

        waves = requestdata['wave']
        for wave in waves:
            PathWaveDesigns.append(GeneralPathResources + wave)

        for coaxial in requestdata.get('coaxial', []):
            PathCoaxialDesigns.append(GeneralPathResources + coaxial)

        tranmissions = requestdata['transmission']
        for trasmission in tranmissions:
            PathTransmissionDesign.append(GeneralPathResources + trasmission)

        max_wind = requestdata['max_wind']
        min_wind = requestdata['min_wind']
        max_kite = requestdata['max_kite']
        min_kite = requestdata['min_kite']
        max_wave = requestdata['max_wave']
        min_wave = requestdata['min_wave']

        lcoe_max = requestdata['lcoe_max']
        lcoe_min = requestdata['lcoe_min']
        lcoe_step = requestdata['lcoe_step']
        max_system_radius = requestdata['max_system_radius']
        WindTurbinesPerSite = requestdata['WindTurbinesPerSite']
        KiteTurbinesPerSite = requestdata['KiteTurbinesPerSite']
        WaveTurbinesPerSite = requestdata['WaveTurbinesPerSite']

        LCOE_RANGE = range(lcoe_max, lcoe_min, -1 * lcoe_step)
        Max_CollectionRadious = max_system_radius
        MaxDesignsWind = max_wind
        MaxDesingsKite = max_kite
        MinNumWindTurb = min_wind
        MinNumKiteTrub = min_kite
        MaxDesingsWave = max_wave
        MinNumWaveTurb = min_wave

        print(PathWindDesigns)
        print(PathKiteDesigns)
        print(PathWaveDesigns)
        print(PathTransmissionDesign)

        def join_after_last_slash(file_list):
            if not file_list:
                return "0"
            extracted_parts = [item.split('/')[-1] for item in file_list]
            result = '#'.join(extracted_parts)
            return result

        SavePaths = []

        for PathTransmissionDesign_i in PathTransmissionDesign:
            for wi, PathWindDesigns_i in tqdm(enumerate(PathWindDesigns)):
                TurbineCaseName = PathWindDesigns_i.rsplit(r"/")[-1][:-4]
                TransmissionCaseName = PathTransmissionDesign_i.rsplit(r"/")[-1][:-4]

                SavePath = os.path.join(
                    PORTFOLIOS_DIR,
                    TransmissionCaseName + "$" + TurbineCaseName + "$" +
                    join_after_last_slash(PathKiteDesigns) + "$" +
                    join_after_last_slash(PathWaveDesigns) + "$" +
                    join_after_last_slash(PathCoaxialDesigns) +
                    f"$max={lcoe_max}$min={lcoe_min}$step={lcoe_step}"
                )

                PerLCOE_OutputFolder = SavePath + "_perLCOE"
                ReadMe = ""
                SavePaths.append(SavePath + '.npz')

                if not os.path.exists(SavePath + '.npz'):
                    SolvePortOpt_MaxGen_LCOE_Iterator(
                        [PathWindDesigns_i], PathWaveDesigns, PathKiteDesigns,
                        PathTransmissionDesign_i, LCOE_RANGE,
                        Max_CollectionRadious, MaxDesignsWind, MaxDesingsWave,
                        MaxDesingsKite, MinNumWindTurb, MinNumWaveTurb,
                        MinNumKiteTrub, ReadMe,
                        SavePath=SavePath,
                        PerLCOE_OutputFolder=PerLCOE_OutputFolder,
                        WindTurbinesPerSite=WindTurbinesPerSite,
                        KiteTurbinesPerSite=KiteTurbinesPerSite,
                        WaveTurbinesPerSite=WaveTurbinesPerSite,
                    )
                else:
                    print(f"{SavePath} already exists")
                print("Done with " + SavePath)

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    return jsonify({'message': 'The server executed this API call.', 'save_path': SavePaths})


@app.route('/portfolioPlots', methods=['POST'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def portfolioPlots():
    try:
        data = request.get_json()
        print(f"Received data: {data}")
    except Exception as e:
        print(f"JSON parse error: {str(e)}")

    required_fields = ['portfolio']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    try:
        requestdata = request.get_json()
        print(requestdata)
        portfolio_location = requestdata['portfolio']
        print("PRINTING => ", portfolio_location)
        portfolio_location = portfolio_location[0].split(PORTFOLIOS_DIR + '/')[-1]
        if portfolio_location == portfolio_location:
            portfolio_location = portfolio_location.split('./OutputData/Portfolios/')[-1]
        print(portfolio_location)

        SolutionPaths = []
        SolutionPaths.append(os.path.join(PORTFOLIOS_DIR, portfolio_location))

        resource_type = {
            '8MW_2020_Vestas': '8MW Vestas 2020',
            '12MW_2030': '12MW 2030',
            '15MW_2030': '15MW 2030',
            '18MW_2030': '18MW 2030',
            'PowerTimeSeriesKite_VD50_BCS0.5': '0.05MW (0.5m/s)',
            'PowerTimeSeriesKite_VD50_BCS0.75': '0.14MW (0.75m/s)',
            'PowerTimeSeriesKite_VD50_BCS1.0': '0.31MW (1.0m/s)',
            'PowerTimeSeriesKite_VD50_BCS1.25': '0.57MW (1.25m/s)',
            'PowerTimeSeriesKite_VD50_BCS1.5': '0.93MW (1.5m/s)',
            'PowerTimeSeriesKite_VD50_BCS1.75': '1.43MW (1.75m/s)',
            'PowerTimeSeriesKite_VD50_BCS2.0': '2.04MW (2.0m/s)',
            'PowerTimeSeriesKite_VD50_BCS2.25': '1.987MW (2.25m/s)',
            'PowerTimeSeriesKite_VD50_BCS2.5': '1.87MW (2.5m/s)',
            'PowerTimeSeriesKite_VD50_BCS2.75': '1.81MW (2.75m/s)',
            'Pelamis': 'Pelamis',
            'RM3': 'RM3',
        }

        resource_names = ""
        for key, val in resource_type.items():
            if key in portfolio_location:
                resource_names += val + '\n'

        print(resource_names)
        Legend = [resource_names]

        linestyle = ['-', '-', '--', '-.', '-', '--', '-.', '-', '--', '-.']
        ColorList = ['tab:orange', 'k', 'k', 'k', "b", "b", "b", "r", "r", "r"]
        Marker = [None] * len(SolutionPaths)

        SavePath = os.path.join(PLOTS_DIR, "UI.png")

        try:
            os.remove(SavePath)
        except Exception:
            print("NO PLOT DETECTED")

        PlotEfficientFrontier(
            SolutionPaths, Legend, linestyle=linestyle,
            ColorList=ColorList, Marker=Marker, Title=None, SavePath=SavePath,
        )

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    if os.path.exists(SavePath):
        return send_file(SavePath, mimetype='image/png', as_attachment=False)
    else:
        return jsonify({"error": f"Plot not found at {SavePath}"}), 404


# ---------------------------------------------------------------------------
# New per-LCOE plot endpoints
# ---------------------------------------------------------------------------

@app.route('/portfolioResults/<path:portfolio_id>/plots', methods=['GET'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def list_portfolio_plots(portfolio_id):
    """List available per-LCOE plots and run-level plots for a portfolio."""
    base_folder = os.path.join(PORTFOLIOS_DIR, portfolio_id + "_perLCOE")
    if not os.path.isdir(base_folder):
        return jsonify({"error": "Portfolio output folder not found", "path": base_folder}), 404

    result = {"run_level": [], "per_lcoe": {}}

    for fname in sorted(os.listdir(base_folder)):
        fpath = os.path.join(base_folder, fname)
        if os.path.isfile(fpath) and (fname.endswith('.png') or fname.endswith('.csv')):
            result["run_level"].append(fname)
        elif os.path.isdir(fpath) and fname.startswith("LCOE_"):
            lcoe_files = [
                f for f in sorted(os.listdir(fpath))
                if f.endswith('.png') or f.endswith('.npz')
            ]
            result["per_lcoe"][fname] = lcoe_files

    return jsonify(result)


PLOT_TYPE_MAP = {
    "totalGeneration": "Plot_TotalGeneration.png",
    "stackedGeneration": "Plot_StackedGenByTech.png",
    "curtailment": "Plot_Curtailment.png",
    "deploymentMap": "Plot_DeploymentMap.png",
}


@app.route('/portfolioResults/<path:portfolio_id>/lcoe/<int:lcoe_target>/<plot_type>', methods=['GET'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def get_lcoe_plot(portfolio_id, lcoe_target, plot_type):
    """Serve a per-LCOE plot PNG."""
    if plot_type not in PLOT_TYPE_MAP:
        return jsonify({"error": f"Unknown plot type: {plot_type}", "valid": list(PLOT_TYPE_MAP.keys())}), 400

    filename = PLOT_TYPE_MAP[plot_type]
    plot_path = os.path.join(
        PORTFOLIOS_DIR, portfolio_id + "_perLCOE",
        f"LCOE_{lcoe_target}", filename
    )

    if os.path.exists(plot_path):
        return send_file(plot_path, mimetype='image/png', as_attachment=False)
    else:
        return jsonify({"error": f"Plot not found at {plot_path}"}), 404


@app.route('/portfolioResults/<path:portfolio_id>/summary', methods=['GET'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def get_portfolio_summary(portfolio_id):
    """Serve the Summary.csv for a portfolio run."""
    csv_path = os.path.join(PORTFOLIOS_DIR, portfolio_id + "_perLCOE", "Summary.csv")
    if os.path.exists(csv_path):
        return send_file(csv_path, mimetype='text/csv', as_attachment=True)
    else:
        return jsonify({"error": f"Summary not found at {csv_path}"}), 404


@app.route('/portfolioResults/<path:portfolio_id>/efficientFrontier', methods=['GET'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def get_efficient_frontier(portfolio_id):
    """Serve the efficient frontier plot for a portfolio run."""
    plot_path = os.path.join(
        PORTFOLIOS_DIR, portfolio_id + "_perLCOE", "Plot_EfficientFrontier.png"
    )
    if os.path.exists(plot_path):
        return send_file(plot_path, mimetype='image/png', as_attachment=False)
    else:
        return jsonify({"error": f"Plot not found at {plot_path}"}), 404


@app.route('/portfolioResults/<path:portfolio_id>/stackedCosts', methods=['GET'])
@cross_origin(origin='*', headers=['Content-Type', 'Authorization'])
def get_stacked_costs(portfolio_id):
    """Serve the stacked costs plot for a portfolio run."""
    plot_path = os.path.join(
        PORTFOLIOS_DIR, portfolio_id + "_perLCOE", "Plot_StackedCosts.png"
    )
    if os.path.exists(plot_path):
        return send_file(plot_path, mimetype='image/png', as_attachment=False)
    else:
        return jsonify({"error": f"Plot not found at {plot_path}"}), 404


if __name__ == '__main__':
    app.run('0.0.0.0', 4000, debug=True)
