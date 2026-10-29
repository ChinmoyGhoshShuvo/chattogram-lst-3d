/*******************************************************************************
 Chattogram District: April–May land surface temperature (LST)
   Landsat 5 TM        2000–2010
   Landsat 8 OLI/TIRS  2015–2025
 Source: USGS Collection 2 Level-2 surface temperature (ST_B6 / ST_B10)
 Harmonisation: Landsat 5 is brought onto the Landsat 8 scale using
                Landsat 7 ETM+ as a bridge (Step 4), because L5 and L8
                never flew at the same time.

 Outputs (Google Drive folder set in FOLDER):
   LST_AprMay_<year>_<sensor>_30m.tif   bands: LST_mean, LST_median (°C), n_obs
                                         nodata = -9999, EPSG:32646, 30 m
   LST_AprMay_yearly_stats.csv           district land median/mean/p95, scene
                                         count and scene dates for each year

 HOW TO RUN
   1. Upload Ctg_Full.shp (with .dbf .shx .prj) as an asset and paste its
      path into DISTRICT_ASSET below.
   2. Click Run. Read the Console: scene counts per year, then the
      harmonisation numbers from Step 4.
   3. If Step 4 says to apply the adjustment, set APPLY_L5_ADJUSTMENT = true,
      paste the suggested value into L5_ADJUSTMENT_C, and click Run again.
   4. Open the Tasks tab and click Run on each export.
*******************************************************************************/

// ============================ 1. SETTINGS ====================================
var DISTRICT_ASSET = 'projects/YOUR-CLOUD-PROJECT/assets/Ctg_Full';

var district = ee.FeatureCollection(DISTRICT_ASSET)
  .filter(ee.Filter.notNull(['ADM2_EN']));      // drops the empty 2nd feature
var aoi = district.geometry();

var YEARS = [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
             2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];

var SEASON_START = '-04-01';
var SEASON_END   = '-06-01';   // end is exclusive -> 1 April to 31 May

var MAX_ST_UNCERTAINTY_K = 5;  // drop pixels whose ST_QA uncertainty is above this
var COLD_REMNANT_C = 7;        // land pixels this much colder than the scene's
                               // land median are treated as missed cloud
var CRS = 'EPSG:32646';        // WGS 84 / UTM 46N
var FOLDER = 'Chattogram_LST_AprMay';

// Harmonisation: fill these in after reading the Step 4 output in the Console.
var APPLY_L5_ADJUSTMENT = false;
var L5_ADJUSTMENT_C = 0.0;     // °C subtracted from every Landsat 5 value

// ============================ 2. PREPARATION =================================
var SENSORS = {
  L5: {id: 'LANDSAT/LT05/C02/T1_L2', st: 'ST_B6'},
  L7: {id: 'LANDSAT/LE07/C02/T1_L2', st: 'ST_B6'},
  L8: {id: 'LANDSAT/LC08/C02/T1_L2', st: 'ST_B10'}
};

// Scale to °C, mask cloud/shadow/snow/uncertain pixels, remove cold cloud remnants.
function makePrep(stBand) {
  return function (img) {
    var qa = img.select('QA_PIXEL');
    var bit = function (b) { return qa.bitwiseAnd(1 << b).neq(0); };
    // bits: 0 fill, 1 dilated cloud, 2 cirrus (L8 only), 3 cloud, 4 shadow, 5 snow
    var clear = bit(0).or(bit(1)).or(bit(2)).or(bit(3)).or(bit(4)).or(bit(5)).not();
    var water = bit(7);
    var uncertainty = img.select('ST_QA').multiply(0.01);            // Kelvin

    var lst = img.select(stBand).multiply(0.00341802).add(149.0).subtract(273.15)
      .rename('LST')
      .updateMask(clear.and(uncertainty.lt(MAX_ST_UNCERTAINTY_K)));

    var landMedian = lst.updateMask(water.not()).reduceRegion({
      reducer: ee.Reducer.median(), geometry: aoi, scale: 120,
      maxPixels: 1e10, bestEffort: true, tileScale: 4
    }).get('LST');

    var filtered = ee.Image(ee.Algorithms.If(
      landMedian,
      lst.updateMask(lst.gte(ee.Number(landMedian).subtract(COLD_REMNANT_C)).or(water)),
      lst));

    return filtered.addBands(water.rename('water'))
      .set('system:time_start', img.get('system:time_start'))
      .set('SPACECRAFT_ID', img.get('SPACECRAFT_ID'));
  };
}

function seasonal(sensor, y) {
  var s = SENSORS[sensor];
  return ee.ImageCollection(s.id)
    .filterBounds(aoi)
    .filterDate(y + SEASON_START, y + SEASON_END)
    .map(makePrep(s.st));
}

function sensorFor(y) { return y <= 2011 ? 'L5' : 'L8'; }

function composite(y) {
  var sensor = sensorFor(y);
  var col = seasonal(sensor, y);
  var lst = col.select('LST');
  var adj = (sensor === 'L5' && APPLY_L5_ADJUSTMENT) ? L5_ADJUSTMENT_C : 0;
  var img = lst.mean().subtract(adj).rename('LST_mean')
    .addBands(lst.median().subtract(adj).rename('LST_median'))
    .addBands(lst.count().rename('n_obs'))
    .toFloat()
    .clip(aoi);
  return {img: img, col: col, sensor: sensor, water: col.select('water').max(), adj: adj};
}

// ============================ 3. EXPORTS =====================================
var vis = {min: 26, max: 44,
  palette: ['000004', '320a5e', '781b6c', 'bb3654', 'ec6824', 'fbb41a', 'fcffa4']};
Map.centerObject(aoi, 9);
Map.addLayer(ee.Image().byte().paint(district, 1, 2), {palette: ['ffffff']}, 'District');

var validYears = [];
YEARS.forEach(function (y) {
  var c = composite(y);
  var n = c.col.size().getInfo();
  print(y + '  ' + c.sensor + ': ' + n + ' scenes in Apr–May');
  if (n === 0) { print('   -> no scenes, year skipped'); return; }
  validYears.push(y);
  Map.addLayer(c.img.select('LST_mean'), vis, 'LST mean ' + y, false);
  Export.image.toDrive({
    image: c.img.unmask(-9999),
    description: 'LST_AprMay_' + y + '_' + c.sensor,
    folder: FOLDER,
    fileNamePrefix: 'LST_AprMay_' + y + '_' + c.sensor + '_30m',
    region: aoi.bounds(),
    scale: 30,
    crs: CRS,
    maxPixels: 1e13,
    fileFormat: 'GeoTIFF',
    formatOptions: {cloudOptimized: true}
  });
});

// Yearly district statistics (land only, water excluded) -> CSV
var statsFC = ee.FeatureCollection(validYears.map(function (y) {
  var c = composite(y);
  var land = c.img.select('LST_mean').updateMask(c.water.not());
  var s = land.reduceRegion({
    reducer: ee.Reducer.median()
      .combine(ee.Reducer.mean(), null, true)
      .combine(ee.Reducer.percentile([95]), null, true)
      .combine(ee.Reducer.count(), null, true),
    geometry: aoi, scale: 90, maxPixels: 1e13, bestEffort: true, tileScale: 4
  });
  var dates = c.col.aggregate_array('system:time_start')
    .map(function (t) { return ee.Date(t).format('YYYY-MM-dd'); });
  return ee.Feature(null, s).set({
    year: y,
    sensor: c.sensor,
    n_scenes: c.col.size(),
    scene_dates: ee.List(dates).join(','),
    l5_adjustment_applied_C: c.adj
  });
}));
print('Yearly statistics (preview)', statsFC);
Export.table.toDrive({
  collection: statsFC,
  description: 'LST_AprMay_yearly_stats',
  folder: FOLDER,
  fileFormat: 'CSV'
});

// ============================ 4. HARMONISATION CHECK =========================
// L5 (ended 2011) and L8 (started 2013) have no overlap, so they cannot be
// compared directly. Landsat 7 overlaps both, so it is used as a bridge:
//   offset57 = median(L5 − L7) over 2000–2010
//   offset87 = median(L8 − L7) over 2013–2016 (before L7's orbit drift
//              made its overpass noticeably earlier)
//   L5 on the L8 scale = L5 − (offset57 − offset87)
// L5 and L7 pass 8 days apart, so each yearly difference also contains
// weather. The median across many years reduces that.
function offsetVsL7(sensor, y) {
  var a = seasonal(sensor, y);
  var b = seasonal('L7', y);
  var d = a.select('LST').mean().subtract(b.select('LST').mean()).rename('d')
    .updateMask(a.select('water').max().not());
  var v = d.reduceRegion({reducer: ee.Reducer.median(), geometry: aoi, scale: 90,
    maxPixels: 1e13, bestEffort: true, tileScale: 4}).get('d');
  return ee.Feature(null, {sensor: sensor, year: y, d: v});
}

function bridge(sensor, years) {
  var feats = [];
  years.forEach(function (y) {
    var na = seasonal(sensor, y).size().getInfo();
    var nb = seasonal('L7', y).size().getInfo();
    if (na > 0 && nb > 0) feats.push(offsetVsL7(sensor, y));
  });
  return ee.FeatureCollection(feats).filter(ee.Filter.notNull(['d']));
}

var l5vsl7 = bridge('L5', [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010]);
var l8vsl7 = bridge('L8', [2013, 2014, 2015, 2016]);

var off57 = ee.Number(l5vsl7.aggregate_array('d').reduce(ee.Reducer.median()));
var off87 = ee.Number(l8vsl7.aggregate_array('d').reduce(ee.Reducer.median()));
var iqr57 = l5vsl7.aggregate_array('d').reduce(ee.Reducer.percentile([25, 75]));

print('---------------- HARMONISATION ----------------');
print('L5 − L7 by year (°C):', l5vsl7.aggregate_array('year'), l5vsl7.aggregate_array('d'));
print('L8 − L7 by year (°C):', l8vsl7.aggregate_array('year'), l8vsl7.aggregate_array('d'));
print('Median L5 − L7 (°C):', off57, '  25th/75th percentile:', iqr57);
print('Median L8 − L7 (°C):', off87);
print('Suggested L5_ADJUSTMENT_C = (L5−L7) − (L8−L7):', off57.subtract(off87));
print('Rule of thumb: apply it only if its size is ≥ 0.5 °C and the yearly ' +
      'L5−L7 values mostly agree in sign.');
