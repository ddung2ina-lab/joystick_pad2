"""Build the eight-key UF2 with the known W25Q32 boot code, without flashing."""
from pathlib import Path
import argparse,os,subprocess,tempfile,shutil,json,hashlib,struct,re
from make_public_uf2 import make_public

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
parser=argparse.ArgumentParser()
parser.add_argument('--toolchain-root',type=Path,default=Path.home()/'AppData/Local/Temp/handpad-arduino-build')
args=parser.parse_args()
base=args.toolchain_root.resolve();cli=base/'arduino-cli.exe'
assert cli.is_file() and (base/'data/packages/rp2040/hardware/rp2040/6.3.2').is_dir()
work=Path(tempfile.mkdtemp(prefix='handpad8_columns_fixed_'))
sketch=work/'Handpad8';shutil.copytree(HERE/'Handpad8',sketch)
output=work/'output';output.mkdir();(work/'user').mkdir()
env=os.environ.copy()
env.update(ARDUINO_DIRECTORIES_DATA=str(base/'data'),ARDUINO_DIRECTORIES_DOWNLOADS=str(base/'downloads'),
           ARDUINO_DIRECTORIES_USER=str(work/'user'))
fqbn='rp2040:rp2040:generic:flash=2097152_0,usbstack=tinyusb'
cmd=[str(cli),'compile','--fqbn',fqbn,'--build-property','build.boot2=boot2_W25Q32JVxQ_4_padded_checksum',
     '--jobs','4','--warnings','default','--build-path',str(work/'build'),'--output-dir',str(output),str(sketch)]
print('Building eight-key firmware with W25Q32 boot2...',flush=True)
run=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
log=run.stdout.decode('utf8',errors='replace')
(HERE/'build.log').write_text(log,encoding='utf8')
print(log[-7000:],flush=True)
assert run.returncode==0,'Compilation failed; see build.log'
raw=(output/'Handpad8.ino.uf2').read_bytes();clean,paths=make_public(raw)
release_dir=ROOT/'.local/release';release_dir.mkdir(parents=True,exist_ok=True)
target=release_dir/'JoystickPad2.uf2';target.write_bytes(clean)

# Verify every UF2 block, contiguous flash, family ID and the emitted button table
# from the ELF symbol, rather than trusting only the source mapping.
flash={};total=len(clean)//512
for i in range(total):
    block=clean[i*512:(i+1)*512];w=struct.unpack_from('<8I',block)
    assert w[:2]==(0x0a324655,0x9e5d5157) and struct.unpack_from('<I',block,508)[0]==0x0ab16f30
    assert w[2]&0x2000 and w[4]==256 and w[5]==i and w[6]==total and w[7]==0xe48bff56
    assert w[3] not in flash
    flash[w[3]]=block[32:288]
start=min(flash);image=b''.join(flash[a] for a in sorted(flash))
assert start==0x10000000 and sorted(flash)==list(range(start,start+len(image),256))
assert raw[32:288]==clean[32:288],'Boot code was altered during path cleanup'
boot_source=base/'data/packages/rp2040/hardware/rp2040/6.3.2/boot2/rp2040/boot2_W25Q32JVxQ_4_padded_checksum.S'
expected_boot=bytes(int(n,16) for line in boot_source.read_text(encoding='utf8').splitlines()
                    if line.lstrip().startswith('.byte') for n in re.findall(r'0x([0-9a-fA-F]{2})',line))
assert len(expected_boot)==256 and image[:256]==expected_boot,'W25Q32 boot fix missing from actual UF2'

elf=(output/'Handpad8.ino.elf').read_bytes()
assert elf[:7]==b'\x7fELF\x01\x01\x01'
eh=struct.unpack_from('<16sHHIIIIIHHHHHH',elf)
phoff,shoff,phsize,phnum,shsize,shnum=eh[5],eh[6],eh[9],eh[10],eh[11],eh[12]
sections=[struct.unpack_from('<10I',elf,shoff+i*shsize) for i in range(shnum)]
symbol=None
for sh in sections:
    if sh[1]!=2:continue
    strings=sections[sh[6]];stringdata=elf[strings[4]:strings[4]+strings[5]]
    for pos in range(sh[4],sh[4]+sh[5],sh[9]):
        n,value,size,info,other,index=struct.unpack_from('<IIIBBH',elf,pos)
        name=stringdata[n:stringdata.find(b'\0',n)]
        if name==b'buttons':symbol=(value,size,index)
assert symbol,'Compiled button table not found'
value,size,index=symbol;sh=sections[index]
filepos=sh[4]+value-sh[3];table=elf[filepos:filepos+size]
config=json.loads((HERE/'mapping.json').read_text(encoding='utf8'))
expected=b''.join(struct.pack('<BBBBI',b['gpio'],b['hid_usage'],0,0,0) for b in config['buttons'])
assert table==expected,'Compiled button table differs from requested layout'
lma=None
for i in range(phnum):
    ph=struct.unpack_from('<8I',elf,phoff+i*phsize)
    if ph[0]==1 and ph[2]<=value and value+size<=ph[2]+ph[4]:lma=ph[3]+value-ph[2]
assert lma is not None and image[lma-start:lma-start+size]==expected,'Delivered UF2 table differs from ELF'
assert config['product'].encode('ascii')+b'\0' in image
assert len(set(b['gpio'] for b in config['buttons']))==9
assert len(set(b['hid_usage'] for b in config['buttons']))==9
digest=hashlib.sha256(clean).hexdigest()
report={'compile_success':True,'fqbn':fqbn,'core':'Arduino-Pico 6.3.2','boot2':config['boot2'],
        'bytes':len(clean),'sha256':digest,'uf2_blocks':total,'family':'RP2040 / 0xE48BFF56',
        'button_table_verified_in_ELF_and_delivered_UF2':True,'button_table_flash_address':hex(lma),
        'buttons':config['buttons'],'sanitized_path_strings':len(paths),'boot2_unchanged_after_cleanup':True,
        'boot2_all_256_bytes_match_W25Q32_source':True,'boot2_sha256':hashlib.sha256(image[:256]).hexdigest(),
        'product':config['product'],'report_bytes':6,'physical_flash_test':False,
        'device_uploaded':False,'axis_orientation_hardware_verified':False,'column_pairs_swapped':True}
(HERE/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
(release_dir/'SHA256SUMS.txt').write_text(digest+'  JoystickPad2.uf2\n',encoding='ascii')
shutil.copy2(output/'Handpad8.ino.elf',HERE/'Handpad8.elf')
print('UF2 VERIFIED:',len(clean),'bytes, SHA256',digest,flush=True)
