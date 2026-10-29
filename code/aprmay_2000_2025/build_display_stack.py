
# Build 90 m display stack + yearly stats from the GEE Apr-May composites (LST_median band)
import os, json, warnings, numpy as np
from osgeo import gdal, ogr
from scipy import ndimage as ndi
BASE=r"path/to/aprmay/project/folder"   # contains "GEE Images/" (the Earth Engine exports)
IMG=os.path.join(BASE,"GEE Images"); R=os.path.join(BASE,"render"); os.makedirs(R,exist_ok=True)
OLD=r"path/to/your/project/folder"   # contains Chattogram_District_boundary.gpkg
files=sorted(f for f in os.listdir(IMG) if f.endswith(".tif"))
ref=gdal.Open(os.path.join(IMG,files[0])); W,H=ref.RasterXSize,ref.RasterYSize; GT=ref.GetGeoTransform(); PRJ=ref.GetProjection()
m=gdal.GetDriverByName("MEM").Create("",W,H,1,gdal.GDT_Byte); m.SetGeoTransform(GT); m.SetProjection(PRJ)
BDS=ogr.Open(os.path.join(OLD,"Chattogram_District_boundary.gpkg")); gdal.RasterizeLayer(m,[1],BDS.GetLayer(),burn_values=[1]); INS=m.ReadAsArray().astype(bool)
wd=gdal.Warp("",os.path.join(OLD,"water_mask.tif"),format="MEM",outputBounds=(GT[0],GT[3]+GT[5]*H,GT[0]+GT[1]*W,GT[3]),xRes=30,yRes=30,dstSRS=PRJ,resampleAlg="near")
WAT=(wd.ReadAsArray()==1)
def blk(a,fn):
    H3,W3=a.shape[0]//3*3,a.shape[1]//3*3
    with warnings.catch_warnings():
        warnings.simplefilter("ignore"); return fn(a[:H3,:W3].reshape(H3//3,3,W3//3,3),axis=(1,3))
gt90=list(GT); gt90[1]*=3; gt90[5]*=3
json.dump({"gt":gt90,"prj":PRJ},open(os.path.join(R,"grid90.json"),"w"))
ins90=blk(INS.astype(float),np.mean)>=0.5; np.save(os.path.join(R,"inside90.npy"),ins90)
w90=blk(WAT.astype(float),np.mean)>0.3
stack=[]; stats=[]
for f in files:
    y=int(f.split("_")[2]); sensor=f.split("_")[3]
    d=gdal.Open(os.path.join(IMG,f)); a=d.GetRasterBand(2).ReadAsArray().astype("float32"); n=d.GetRasterBand(3).ReadAsArray()
    a[(~np.isfinite(a))|(a==-9999)]=np.nan; a[~INS]=np.nan
    land=a[INS&~WAT&np.isfinite(a)]
    nn=n[INS&np.isfinite(a)]
    stats.append(dict(year=y,sensor=sensor,coverage=round(float(np.isfinite(a[INS]).mean()),4),
        land_median=round(float(np.median(land)),2),land_mean=round(float(land.mean()),2),land_p95=round(float(np.percentile(land,95)),2),
        nobs_median=float(np.nanmedian(nn)),nobs_max=float(np.nanmax(nn))))
    b=blk(a,np.nanmean)
    mm=gdal.GetDriverByName("MEM").Create("",b.shape[1],b.shape[0],1,gdal.GDT_Float32); mm.SetGeoTransform(gt90); bd=mm.GetRasterBand(1); bd.SetNoDataValue(-9999)
    bd.WriteArray(np.where(np.isfinite(b)&ins90,b,-9999)); gdal.FillNodata(bd,None,80,0); fl=bd.ReadAsArray(); fl[(~ins90)|(fl==-9999)]=np.nan
    ff=np.where(np.isfinite(fl),fl,np.nanmedian(fl)); lm=ndi.median_filter(ff,size=21)
    bad=(fl<lm-3.5)&~w90&ins90; fl[bad]=lm[bad]
    stack.append(fl); print(stats[-1], "despeckled %.2f%%"%(bad.sum()/ins90.sum()*100))
np.save(os.path.join(R,"lst90_stack_display.npy"),np.stack(stack).astype("float32"))
json.dump(stats,open(os.path.join(BASE,"yearly_summary.json"),"w"),indent=1)
