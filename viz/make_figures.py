"""
Figures built directly from the yearly 30 m April LST composites (LST_April_<year>_30m.tif)
and water_mask.tif produced by code/build_april_lst.py. Land pixels only (water excluded).

Put the GeoTIFFs in a folder and pass it:   python make_figures.py <folder_with_tifs>
Outputs -> ../images/ and data/yearly_land_stats.csv
"""
import sys
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import TwoSlopeNorm

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
HERE = Path(__file__).parent
OUT = HERE.parent / "images"
YEARS = list(range(2015, 2026))
CAUTION = {2016, 2019}  # flagged "read with care" in the build notes (cloud-affected patches)
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "savefig.dpi": 200, "savefig.bbox": "tight", "figure.facecolor": "white",
})

water = rasterio.open(SRC / "water_mask.tif").read(1) == 1


def block(a, k=3):
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    b = a[:h, :w].reshape(h // k, k, w // k, k)
    with np.errstate(all="ignore"):
        return np.nanmean(b, axis=(1, 3))


stats, anoms, hot = [], [], []
for y in YEARS:
    a = rasterio.open(SRC / f"LST_April_{y}_30m.tif").read(1).astype("float32")
    a[(a == -9999) | water] = np.nan
    v = a[~np.isnan(a)]
    med = np.median(v)
    p = np.percentile(v, [5, 25, 50, 75, 95])
    stats.append(dict(year=y, p5=p[0], p25=p[1], median=p[2], p75=p[3], p95=p[4], mean=v.mean(), n_pixels=v.size))
    anom = a - med
    anoms.append(block(anom))
    hot.append(block((a >= p[4]).astype("float32") * np.where(np.isnan(a), np.nan, 1)))
    del a
st = pd.DataFrame(stats)
st.round(3).to_csv(HERE / "data" / "yearly_land_stats.csv", index=False)

# ---------- Figure 1: small multiples of LST relative to each year's district median
norm = TwoSlopeNorm(vmin=-6, vcenter=0, vmax=10)
fig, axes = plt.subplots(2, 6, figsize=(12, 6.2), gridspec_kw={"wspace": 0.02, "hspace": 0.12})
for ax, y, an in zip(axes.flat, YEARS, anoms):
    im = ax.imshow(an, cmap="RdBu_r", norm=norm, interpolation="nearest")
    ax.set_title(f"{y}{' *' if y in CAUTION else ''}", fontsize=9)
    ax.axis("off")
axes.flat[-1].axis("off")
cax = fig.add_axes([0.83, 0.13, 0.012, 0.3])
cb = fig.colorbar(im, cax=cax, extend="both")
cb.set_label("°C relative to that year's\ndistrict median land LST", fontsize=8)
fig.suptitle("Where April heat concentrates in Chattogram District, 2015–2025 (Landsat 8/9, 90 m display)",
             x=0.12, ha="left", fontweight="bold", fontsize=11, y=0.97)
fig.text(0.12, 0.05, "Removing each year's district median takes out year-to-year weather, so colour shows relative heat. "
         "* 2016 and 2019 contain cloud-affected cold patches.", fontsize=7.5, color="#555")
fig.savefig(OUT / "lst-relative-heat-small-multiples-2015-2025.png")
plt.close(fig)

# ---------- Figure 2: persistence of the hottest 5 %
freq = np.nansum(np.stack(hot), axis=0)
valid = ~np.all(np.isnan(np.stack(hot)), axis=0)
freq = np.where(valid, freq, np.nan)
mean_anom = np.nanmean(np.stack(anoms), axis=0)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 6.2), gridspec_kw={"wspace": 0.05})
i1 = a1.imshow(mean_anom, cmap="RdBu_r", norm=norm, interpolation="nearest")
a1.set_title("a  Mean relative LST, 2015–2025", loc="left")
a1.axis("off")
fig.colorbar(i1, ax=a1, shrink=0.55, extend="both").set_label("°C vs yearly district median", fontsize=8)
i2 = a2.imshow(freq, cmap="magma_r", vmin=0, vmax=11, interpolation="nearest")
a2.set_title("b  Years in the district's hottest 5 %", loc="left")
a2.axis("off")
fig.colorbar(i2, ax=a2, shrink=0.55, ticks=[0, 2, 4, 6, 8, 10]).set_label("number of years (of 11)", fontsize=8)
fig.text(0.1, 0.06, "Computed from the 30 m composites (land only), shown as 90 m block means. "
         "Persistent hot ground marks the metropolitan core, port and industrial belts.", fontsize=7.5, color="#555")
fig.savefig(OUT / "lst-hotspot-persistence-2015-2025.png")
plt.close(fig)

# ---------- Figure 3: yearly distribution
fig, ax = plt.subplots(figsize=(7.4, 3.2))
for _, r in st.iterrows():
    c = "#999999" if r.year in CAUTION else "#D55E00"
    ax.plot([r.year, r.year], [r.p5, r.p95], color=c, lw=1.2)
    ax.add_patch(plt.Rectangle((r.year - 0.3, r.p25), 0.6, r.p75 - r.p25, facecolor=c, alpha=0.35, edgecolor=c,
                               hatch="///" if r.year in CAUTION else None))
    ax.plot([r.year - 0.3, r.year + 0.3], [r["median"], r["median"]], color=c, lw=2)
ax.set_xticks(YEARS)
ax.set_ylabel("April land surface temperature (°C)")
ax.set_xlim(2014.4, 2025.6)
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("District land LST by year: median, interquartile box, 5th–95th percentile", loc="left")
fig.text(0, -0.05, "Grey hatched = read with care (2016, 2019). Year-to-year shifts mainly reflect pre-monsoon weather, "
         "not a warming trend.", fontsize=7.5, color="#555")
fig.savefig(OUT / "lst-yearly-distribution-2015-2025.png")
plt.close(fig)
print(st.round(2))
