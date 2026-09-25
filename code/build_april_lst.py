
# April median Landsat LST composites for Chattogram District, 2015-2025
# Source: Landsat Collection 2 Level-2 (ST_B10 + QA_PIXEL) via Microsoft Planetary Computer
import os, json, time, urllib.request, urllib.parse, traceback
import numpy as np
from osgeo import gdal, ogr, osr
gdal.UseExceptions()
gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN","EMPTY_DIR")
gdal.SetConfigOption("GDAL_HTTP_MAX_RETRY","5"); gdal.SetConfigOption("GDAL_HTTP_RETRY_DELAY","3")
OUT=r"C:\Users\Chinmoy Gosh\Documents\Chattogram_LST_3D\district_2015_2025"
BND=os.path.join(OUT,"Chattogram_District_boundary.gpkg")
LOG=os.path.join(OUT,"processing_log.txt")
STAC="https://planetarycomputer.microsoft.com/api/stac/v1"
def log(*a):
    with open(LOG,"a",encoding="utf-8") as f: f.write(time.strftime("%H:%M:%S ")+" ".join(str(x) for x in a)+"\n")
def post(url,body):
    return json.load(urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}),timeout=90))
def sign(h):
    return json.load(urllib.request.urlopen(STAC.replace("/stac/v1","/sas/v1/sign")+"?href="+urllib.parse.quote(h,safe=""),timeout=60))["href"]

# grid from boundary envelope (UTM 46N, 30 m)
v=ogr.Open(BND); L=v.GetLayer(); xmin,xmax,ymin,ymax=L.GetExtent()
xmin=np.floor(xmin/30)*30-300; ymin=np.floor(ymin/30)*30-300; xmax=np.ceil(xmax/30)*30+300; ymax=np.ceil(ymax/30)*30+300
W=int((xmax-xmin)/30); H=int((ymax-ymin)/30); GT=(xmin,30,0,ymax,0,-30)
srs=osr.SpatialReference(); srs.ImportFromEPSG(32646); WKT=srs.ExportToWkt()
m=gdal.GetDriverByName("MEM").Create("",W,H,1,gdal.GDT_Byte); m.SetGeoTransform(GT); m.SetProjection(WKT)
gdal.RasterizeLayer(m,[1],L,burn_values=[1]); INSIDE=m.ReadAsArray().astype(bool); m=None
BBOX=[91.30,21.85,92.23,23.00]
log("grid",W,H,"inside px",INSIDE.sum())

def fetch(item):
    arrs={}
    for key in ["lwir11","qa_pixel"]:
        href=sign(item["assets"][key]["href"])
        ds=gdal.Warp("", "/vsicurl/"+href, format="MEM", outputBounds=(xmin,ymin,xmax,ymax), xRes=30, yRes=30, dstSRS=WKT, resampleAlg="near", dstNodata=0)
        arrs[key]=ds.GetRasterBand(1).ReadAsArray(); ds=None
    dn=arrs["lwir11"].astype("float32"); qa=arrs["qa_pixel"].astype("uint16")
    lst=dn*0.00341802+149.0-273.15
    bad=(dn==0)|(qa==1)|(((qa>>1)|(qa>>2)|(qa>>3)|(qa>>4)|(qa>>5))&1==1)
    lst[bad]=np.nan
    water=((qa>>7)&1==1)&~bad
    # remove cloud remnants the QA band missed: land pixels >7 C colder than this scene's land median
    land=np.isfinite(lst)&~water&INSIDE
    if land.sum()>10000:
        lst[(lst<np.median(lst[land])-7.0)&~water]=np.nan
    return lst, water

def search(d0,d1):
    body={"collections":["landsat-c2-l2"],"bbox":BBOX,"datetime":f"{d0}/{d1}","limit":100,
          "query":{"platform":{"in":["landsat-8","landsat-9"]},"eo:cloud_cover":{"lt":80}}}
    return post(STAC+"/search",body)["features"]

def save(path,arr,dtype=gdal.GDT_Float32,nd=-9999):
    d=gdal.GetDriverByName("GTiff").Create(path,W,H,1,dtype,["COMPRESS=DEFLATE","PREDICTOR=2" if dtype==gdal.GDT_Float32 else "PREDICTOR=1","TILED=YES"])
    d.SetGeoTransform(GT); d.SetProjection(WKT); b=d.GetRasterBand(1); b.SetNoDataValue(nd); b.WriteArray(arr); d=None

summary=[]
YEARS=globals().get("YEARS", list(range(2015,2026)))
for y in YEARS:
    try:
        stack=[]; wcount=np.zeros((H,W),"uint8"); used=[]
        for it in sorted(search(f"{y}-04-01",f"{y}-04-30"), key=lambda f:f["id"]):
            lst,water=fetch(it); stack.append(lst); wcount+=water; used.append(it["id"]); log(y,"got",it["id"])
        cov=float((np.isfinite(np.nanmax(np.stack(stack),0)) & INSIDE).sum()/INSIDE.sum()) if stack else 0.0
        window="Apr 1-30"
        if cov<0.95:
            log(y,"April coverage",round(cov,3),"-> widening to 15 Mar-15 May")
            extra=[f for f in search(f"{y}-03-15",f"{y}-05-15") if f["id"] not in used]
            for it in sorted(extra,key=lambda f:f["id"]):
                lst,water=fetch(it); stack.append(lst); wcount+=water; used.append(it["id"]); log(y,"got extra",it["id"])
            window="15 Mar-15 May"
            cov2=float((np.isfinite(np.nanmax(np.stack(stack),0)) & INSIDE).sum()/INSIDE.sum())
            if cov2<0.95:
                log(y,"coverage still",round(cov2,3),"-> widening to 1 Mar-31 May")
                extra=[f for f in search(f"{y}-03-01",f"{y}-05-31") if f["id"] not in used]
                for it in sorted(extra,key=lambda f:f["id"]):
                    lst,water=fetch(it); stack.append(lst); wcount+=water; used.append(it["id"]); log(y,"got extra",it["id"])
                window="1 Mar-31 May"
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore"); med=np.nanmedian(np.stack(stack),0)
        nobs=np.isfinite(np.stack(stack)).sum(0).astype("uint8")
        cov=float((np.isfinite(med)&INSIDE).sum()/INSIDE.sum())
        med[~INSIDE]=np.nan
        waterm=(wcount>0)&INSIDE
        landv=med[INSIDE & ~waterm & np.isfinite(med)]
        dmed=float(np.median(landv))
        out=np.where(np.isfinite(med),med,-9999).astype("float32")
        save(os.path.join(OUT,f"LST_April_{y}_30m.tif"),out)
        save(os.path.join(OUT,f"nobs_April_{y}.tif"),np.where(INSIDE,nobs,255).astype("uint8"),gdal.GDT_Byte,255)
        if y==YEARS[0] or not os.path.exists(os.path.join(OUT,"water_mask.tif")):
            save(os.path.join(OUT,"water_mask.tif"),waterm.astype("uint8"),gdal.GDT_Byte,255)
        rec=dict(year=y,window=window,scenes=len(used),coverage=round(cov,4),land_median=round(dmed,2),
                 land_p95=round(float(np.percentile(landv,95)),2),land_mean=round(float(landv.mean()),2),ids=used)
        summary.append(rec); log(y,"DONE",json.dumps({k:v for k,v in rec.items() if k!="ids"}))
        json.dump(summary,open(os.path.join(OUT,"composite_summary.json"),"w"),indent=1)
        del stack
    except Exception:
        log(y,"ERROR",traceback.format_exc())
log("ALL FINISHED")
