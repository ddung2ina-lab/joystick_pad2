"""Remove absolute build-user paths from diagnostic strings in an RP2040 UF2.

Usage: python firmware/make_public_uf2.py build/JoystickPad.ino.uf2 JoystickPad.uf2
Only NUL-terminated path strings are replaced; addresses and instructions stay put.
"""
import argparse
import hashlib
from pathlib import Path
import re
import struct


def make_public(source):
    data=bytearray(source)
    assert len(data)%512==0, 'UF2 blocks must be 512 bytes'
    blocks=[]
    for pos in range(0,len(data),512):
        words=struct.unpack_from('<8I',data,pos)
        assert words[:2]==(0x0a324655,0x9e5d5157)
        assert struct.unpack_from('<I',data,pos+508)[0]==0x0ab16f30
        assert words[4]==256 and words[7]==0xe48bff56, 'Expected RP2040 flash UF2'
        blocks.append((words[3],pos))
    blocks.sort()
    base=blocks[0][0]
    assert all(addr==base+i*256 for i,(addr,_) in enumerate(blocks)), 'Expected contiguous flash'
    flash=bytearray().join(data[pos+32:pos+288] for _,pos in blocks)
    before=bytes(flash)
    replacements=[]
    pattern=rb'[A-Za-z]:[\\/](?:Users|home)[\\/][^\x00\r\n]+'
    for match in re.finditer(pattern,before,re.I):
        assert match.end()<len(before) and before[match.end()]==0
        assert all(32<=c<=126 for c in match.group()), 'Unexpected non-ASCII path'
        basename=re.split(rb'[\\/]',match.group())[-1]
        replacement=b'core/'+basename
        assert len(replacement)<=len(match.group())
        flash[match.start():match.end()]=replacement.ljust(len(match.group()),b'\0')
        replacements.append((match.start(),match.end(),basename.decode('ascii')))
    allowed=set(i for start,end,_ in replacements for i in range(start,end))
    assert all(i in allowed for i,(a,b) in enumerate(zip(before,flash)) if a!=b)
    assert flash[:256]==before[:256], 'Boot code must remain unchanged'
    for i,(_,pos) in enumerate(blocks):data[pos+32:pos+288]=flash[i*256:(i+1)*256]
    assert not re.search(pattern,flash,re.I)
    return bytes(data),[name for _,_,name in replacements]


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    clean,names=make_public(args.input.read_bytes())
    args.output.write_bytes(clean)
    print('Sanitized diagnostic paths:',len(names))
    print('SHA256:',hashlib.sha256(clean).hexdigest())
