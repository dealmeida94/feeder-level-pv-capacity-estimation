#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#@author: matheus

def calc_tempo (begin, end):
    tempo = end - begin
    minutos = int(tempo // 60)
    segundos = int(tempo % 60)

    return (f"{minutos:02d}m:{segundos:02d}s")