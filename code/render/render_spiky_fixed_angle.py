
import os, json, numpy as np
from osgeo import gdal
from qgis.core import *
from qgis._3d import *
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize
D=r"C:\Users\Chinmoy Gosh\Documents\Chattogram_LST_3D\district_2015_2025"; R=os.path.join(D,"render"); FR=os.path.join(R,"tmp2")
os.makedirs(FR,exist_ok=True)
g=json.load(open(os.path.join(R,"grid90.json"))); INS=np.load(os.path.join(R,"inside90.npy"))
def box(a,k):
    p=np.pad(a,k//2,mode="edge"); c=p.cumsum(0).cumsum(1); c=np.pad(c,((1,0),(1,0)))
    return (c[k:,k:]-c[:-k,k:]-c[k:,:-k]+c[:-k,:-k])/(k*k)
FLOOR=-2.5
def height_from(lst, med, smooth=3, pos_pow=1.3, neg_scale=0.3):
    a=np.where(INS,np.nan_to_num(lst-med),0.0)
    if smooth>1: a=box(a,smooth)
    pos=np.clip(a,0,None)**pos_pow; neg=np.clip(a,None,0)*neg_scale
    h=np.clip(pos+neg,FLOOR,22)
    return np.where(INS,h,FLOOR-0.3).astype("float32")
def prep(**kw):
    S=np.load(os.path.join(R,"lst90_stack_display.npy")); summ=json.load(open(os.path.join(D,"composite_summary.json")))
    meds=np.array([x["land_median"] for x in summ],"float32")
    Hs=np.stack([height_from(S[i],meds[i],**kw) for i in range(S.shape[0])])
    return S,Hs,meds,[x["year"] for x in summ]
def ease(u): return u*u*(3-2*u)
def write(path,arr):
    d=gdal.GetDriverByName("GTiff").Create(path,arr.shape[1],arr.shape[0],1,gdal.GDT_Float32)
    d.SetGeoTransform(g["gt"]); d.SetProjection(g["prj"]); b=d.GetRasterBand(1); b.SetNoDataValue(-9999); b.WriteArray(arr); d=None
def style(lyr, lo=26.0, hi=44.0):
    cols=["#000004","#320a5e","#781b6c","#bb3654","#ec6824","#fbb41a","#fcffa4"]
    sh=QgsColorRampShader(lo,hi); sh.setColorRampType(QgsColorRampShader.Interpolated)
    sh.setColorRampItemList([QgsColorRampShader.ColorRampItem(lo+(hi-lo)*i/6,QColor(c)) for i,c in enumerate(cols)]); sh.setClip(False)
    rs=QgsRasterShader(); rs.setRasterShaderFunction(sh); r=QgsSingleBandPseudoColorRenderer(lyr.dataProvider(),1,rs)
    r.setClassificationMin(lo); r.setClassificationMax(hi); r.setNodataColor(QColor("#101019")); lyr.setRenderer(r)
def setup():
    prj=QgsProject.instance(); prj.clear(); prj.setCrs(QgsCoordinateReferenceSystem("EPSG:32646"))
    bl=QgsVectorLayer(os.path.join(D,"Chattogram_District_boundary.gpkg")+"|layername=district","District","ogr"); prj.addMapLayer(bl)
    ext=bl.extent(); ext.grow(3000)
    ms=Qgs3DMapSettings(); ms.setCrs(prj.crs()); ms.setExtent(ext); ms.setOrigin(QgsVector3D(ext.center().x(),ext.center().y(),0))
    ms.setTransformContext(prj.transformContext()); ms.setPathResolver(prj.pathResolver()); ms.setMapThemeCollection(prj.mapThemeCollection())
    bg=QgsFixedGradientBackgroundSettings(); bg.setTopColor(QColor("#161625")); bg.setBottomColor(QColor("#07070c")); ms.setBackgroundSettings(bg)
    ms.setMaxTerrainScreenError(1.0); ms.setMapTileResolution(1024)
    lm=prj.layoutManager(); L=QgsPrintLayout(prj); L.initializeDefaults(); L.setName("D3D"); lm.addLayout(L)
    L.pageCollection().page(0).setPageSize(QgsLayoutSize(1920,1080,QgsUnitTypes.LayoutPixels))
    L.pageCollection().page(0).setPageStyleSymbol(QgsFillSymbol.createSimple({"color":"#07070c","outline_style":"no"}))
    it=QgsLayoutItem3DMap(L); L.addLayoutItem(it); it.attemptMove(QgsLayoutPoint(0,0,QgsUnitTypes.LayoutPixels)); it.attemptResize(QgsLayoutSize(1920,1080,QgsUnitTypes.LayoutPixels))
    it.setMapSettings(ms)
    return it, L
PREV=[]
def render_frame(k, yf, item, layout, S, Hs, out_jpg, VS=380.0, dist=175000, pitch=58, heading=345, cx=0, cy=0, size=(1920,1080)):
    global PREV
    i=int(np.floor(yf)); i=min(i,S.shape[0]-1); u=yf-i
    if u>1e-6 and i+1<S.shape[0]:
        e=ease(u); c=(1-e)*S[i]+e*S[i+1]; h=(1-e)*Hs[i]+e*Hs[i+1]
    else: c=S[i]; h=Hs[i]
    cp_=os.path.join(FR,f"c_{k:04d}.tif"); hp=os.path.join(FR,f"h_{k:04d}.tif")
    write(cp_, np.where(INS&np.isfinite(c),c,-9999).astype("float32")); write(hp, h)
    prj=QgsProject.instance()
    cl=QgsRasterLayer(cp_,f"c{k}"); style(cl); hl=QgsRasterLayer(hp,f"h{k}")
    prj.addMapLayer(cl,False); prj.addMapLayer(hl,False)
    ms=item.mapSettings()
    ms.setLayers([cl]); ts=QgsDemTerrainSettings(); ts.setLayer(hl); ts.setVerticalScale(VS); ts.setResolution(256); ts.setSkirtHeight(0.0); ms.setTerrainSettings(ts)
    c0=ms.extent().center(); ms.setOrigin(QgsVector3D(c0.x(),c0.y(),0))
    cp=QgsCameraPose(); cp.setCenterPoint(QgsVector3D(cx,cy,300)); cp.setDistanceFromCenterPoint(dist); cp.setPitchAngle(pitch); cp.setHeadingAngle(heading); item.setCameraPose(cp); item.refresh()
    st=QgsLayoutExporter.ImageExportSettings(); st.imageSize=QSize(*size)
    r=QgsLayoutExporter(layout).exportToImage(out_jpg,st)
    for lid in PREV:
        lyr=prj.mapLayer(lid); src=lyr.source() if lyr else None
        prj.removeMapLayer(lid)
        if src and os.path.exists(src):
            try: os.remove(src)
            except Exception: pass
    PREV=[cl.id(),hl.id()]
    return r
