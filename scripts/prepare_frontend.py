from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'frontend/node_modules';target=ROOT/'frontend/vendor';target.mkdir(exist_ok=True)
for package,path,dest in [('leaflet','dist/leaflet.js','leaflet.js'),('leaflet','dist/leaflet.css','leaflet.css'),('echarts','dist/echarts.min.js','echarts.min.js')]:
    shutil.copyfile(source/package/path,target/dest)
shutil.copytree(source/'leaflet/dist/images',target/'images',dirs_exist_ok=True)
for package in ['leaflet','echarts']:
    license_path=source/package/'LICENSE'
    if license_path.exists():shutil.copyfile(license_path,target/(package+'-LICENSE'))
print('Local frontend assets ready.')
