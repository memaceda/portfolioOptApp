import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import xarray as xr
from matplotlib.lines import Line2D
from matplotlib.colors import BoundaryNorm, ListedColormap

# =============================================================
# USER CONFIGURATION
# =============================================================

# --- Turbine design file (the .npz you already have) ---
TURBINE_NPZ = r"C:\Users\rmiller9\Documents\East Coast Model\Tech Outputs\Wind\GenPU_ATB_18MW_2030EastCoast.npz"
TURBINE_NAME = "ATB 18 MW (2030)"

# --- Geospatial overlays (same files you already use) ---
DEPTH_NC    = r"C:\Users\rmiller9\Documents\East Coast Model\Depths_EastCoast_Offshore.nc"
COAST_SHP   = r"C:\Users\rmiller9\Documents\East Coast Model\Geospatial Data\CoastLine\ne_10m_coastline.shp"
BORDERS_SHP = r"C:\Users\rmiller9\Documents\East Coast Model\Geospatial Data\CoastLine\ne_10m_admin_1_states_provinces_lines.shp"

# --- Set to a folder path to save PNGs, or None to just display ---
SAVE_DIR = None   # e.g. r"C:\Users\rmiller9\Documents\East Coast Model\Plots"

# =============================================================
# LOAD TURBINE DATA
# =============================================================
Data = np.load(TURBINE_NPZ, allow_pickle=True)

LatLong        = Data["LatLong"]           # (N, 2)  col 0 = lat, col 1 = lon
WindEnergy_pu  = Data["Energy_pu"]         # (T, N)
AnnualizedCost = Data["AnnualizedCost"]    # (N,)    M$/yr
RatedPower     = float(Data["RatedPower"]) # MW

# TRG may or may not be present
HAS_TRG = "TRG_site" in Data
TRG_site = Data["TRG_site"] if HAS_TRG else None

Data.close()

lat = LatLong[:, 0]
lon = LatLong[:, 1]

# --- Derived quantities ---
CF   = np.mean(WindEnergy_pu, axis=0)                                      # [pu]
LCOE = AnnualizedCost * 1e6 / (CF * RatedPower * 365 * 24)                # [$/MWh]

# =============================================================
# LOAD GEOSPATIAL OVERLAYS  (identical to your wind-speed script)
# =============================================================

# Depth
ds = xr.open_dataset(DEPTH_NC)
lat_d = ds["lat"].values
lon_d = ds["lon"].values
depth = ds["depth"].values

STRIDE = 2
lat_d = lat_d[::STRIDE]
lon_d = lon_d[::STRIDE]
depth = depth[::STRIDE, ::STRIDE]
LonGrid, LatGrid = np.meshgrid(lon_d, lat_d)

DEPTH_LEVELS = [30, 100, 500, 1000, 2000]
DEPTH_COLORS = {
    30:   "purple",
    100:  "royalblue",
    500:  "teal",
    1000: "darkorange",
    2000: "gold",
}

# Coastlines & borders
coast   = gpd.read_file(COAST_SHP)
borders = gpd.read_file(BORDERS_SHP)
coast   = coast.set_crs(epsg=4326)   if coast.crs is None   else coast.to_crs(epsg=4326)
borders = borders.set_crs(epsg=4326) if borders.crs is None else borders.to_crs(epsg=4326)

# Domain padding (shared by all plots)
PAD = 1.0
XLIM = (lon.min() - PAD, lon.max() + PAD)
YLIM = (lat.min() - PAD, lat.max() + PAD)


# =============================================================
# REUSABLE PLOTTING HELPERS
# =============================================================

def _add_overlays(ax):
    """Depth contours, coastline, borders, and depth legend."""
    for lvl in DEPTH_LEVELS:
        cs = ax.contour(
            LonGrid, LatGrid, depth,
            levels=[lvl],
            colors=[DEPTH_COLORS[lvl]],
            linewidths=1.5,
            zorder=3,
        )
        ax.clabel(cs, inline=True, fontsize=8, fmt={lvl: f"{lvl} m"})

    coast.plot(ax=ax, linewidth=1.2, color="black", zorder=5, antialiased=False)
    borders.plot(ax=ax, linewidth=0.6, color="black", zorder=5, antialiased=False)

    legend_lines = [
        Line2D([0], [0], color=DEPTH_COLORS[lvl], lw=2, label=f"{lvl} m")
        for lvl in DEPTH_LEVELS
    ]
    ax.legend(
        handles=legend_lines,
        title="Bathymetry Contours",
        loc="lower right",
        frameon=True,
        framealpha=0.9,
        facecolor="white",
    )

    ax.set_xlim(XLIM)
    ax.set_ylim(YLIM)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")


def plot_continuous(values, cbar_label, title, cmap="viridis", vmin=None, vmax=None,
                    save_name=None):
    """Scatter plot with continuous colorbar + all overlays."""
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.set_facecolor("aliceblue")

    sc = ax.scatter(
        lon, lat, c=values, s=12,
        cmap=cmap,
        vmin=vmin if vmin is not None else np.nanmin(values),
        vmax=vmax if vmax is not None else np.nanmax(values),
        zorder=1,
    )
    cbar = plt.colorbar(sc, ax=ax, shrink=0.85)
    cbar.set_label(cbar_label)

    _add_overlays(ax)
    ax.set_title(title)
    plt.tight_layout()

    if SAVE_DIR and save_name:
        import os
        plt.savefig(os.path.join(SAVE_DIR, save_name), dpi=200, bbox_inches="tight")
        print(f"  Saved → {os.path.join(SAVE_DIR, save_name)}")

    plt.show()


def plot_categorical(values, title, save_name=None):
    """Scatter plot with discrete/categorical colormap for TRG classes."""
    classes = np.unique(values[~np.isnan(values)]).astype(int)
    n_classes = len(classes)

    # Discrete colormap
    cmap = plt.cm.get_cmap("tab10", n_classes)
    norm = BoundaryNorm(
        boundaries=np.arange(classes.min() - 0.5, classes.max() + 1.5, 1),
        ncolors=n_classes,
    )

    fig, ax = plt.subplots(figsize=(11, 9))
    ax.set_facecolor("aliceblue")

    sc = ax.scatter(lon, lat, c=values, s=12, cmap=cmap, norm=norm, zorder=1)

    cbar = plt.colorbar(sc, ax=ax, shrink=0.85, ticks=classes)
    cbar.set_label("TRG Class")
    cbar.ax.set_yticklabels([f"TRG {int(c)}" for c in classes])

    _add_overlays(ax)
    ax.set_title(title)
    plt.tight_layout()

    if SAVE_DIR and save_name:
        import os
        plt.savefig(os.path.join(SAVE_DIR, save_name), dpi=200, bbox_inches="tight")
        print(f"  Saved → {os.path.join(SAVE_DIR, save_name)}")

    plt.show()


# =============================================================
# GENERATE THE FOUR PLOTS
# =============================================================

# 1) Capacity Factor
plot_continuous(
    CF,
    cbar_label="Capacity Factor [pu]",
    title=f"Capacity Factor — {TURBINE_NAME} — East Coast",
    cmap="plasma",
    save_name="CF_map.png",
)

# 2) Annualized Cost
plot_continuous(
    AnnualizedCost,
    cbar_label="Annualized Cost [M$/yr]",
    title=f"Annualized Cost — {TURBINE_NAME} — East Coast",
    cmap="YlOrRd",
    save_name="AnnualizedCost_map.png",
)

# 3) LCOE
plot_continuous(
    LCOE,
    cbar_label="LCOE [$/MWh]",
    title=f"LCOE — {TURBINE_NAME} — East Coast",
    cmap="RdYlGn_r",
    save_name="LCOE_map.png",
)

# 4) TRG Classification
if HAS_TRG:
    plot_categorical(
        TRG_site,
        title=f"TRG Classification — {TURBINE_NAME} — East Coast",
        save_name="TRG_map.png",
    )
else:
    print("\n⚠️  TRG_site not found in the .npz file — skipping TRG plot.")
    print("    Available keys:", list(np.load(TURBINE_NPZ, allow_pickle=True).keys()))

# Cleanup
ds.close()
