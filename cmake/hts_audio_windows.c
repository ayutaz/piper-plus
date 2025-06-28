/* ----------------------------------------------------------------- */
/*           The HMM-Based Speech Synthesis Engine "hts_engine API"  */
/*           developed by HTS Working Group                          */
/*           http://hts-engine.sourceforge.net/                      */
/* ----------------------------------------------------------------- */
/*                                                                   */
/*  Copyright (c) 2001-2015  Nagoya Institute of Technology          */
/*                           Department of Computer Science          */
/*                                                                   */
/*                2001-2008  Tokyo Institute of Technology           */
/*                           Interdisciplinary Graduate School of    */
/*                           Science and Engineering                 */
/*                                                                   */
/* All rights reserved.                                              */
/* ----------------------------------------------------------------- */

/* Windows version of HTS_audio.c - No audio output support */

#include <stdio.h>
#include <stdlib.h>
#include "HTS_hidden.h"

/* HTS_Audio_open: open audio device */
void HTS_Audio_open(HTS_Audio * audio, int sampling_frequency, int max_buff_size)
{
   audio->sampling_frequency = sampling_frequency;
   audio->max_buff_size = max_buff_size;
   audio->buff = NULL;
   audio->buff_size = 0;
   audio->audio_interface = NULL;
   
   /* No audio device on Windows for now */
   return;
}

/* HTS_Audio_set_parameter: set audio parameter */
void HTS_Audio_set_parameter(HTS_Audio * audio, int sampling_frequency, int max_buff_size)
{
   if (audio->sampling_frequency != sampling_frequency || audio->max_buff_size != max_buff_size) {
      HTS_Audio_close(audio);
      HTS_Audio_open(audio, sampling_frequency, max_buff_size);
   }
}

/* HTS_Audio_write: send data to audio device */
void HTS_Audio_write(HTS_Audio * audio, short *buff, int buff_size)
{
   /* No audio output on Windows */
   return;
}

/* HTS_Audio_flush: flush remain data */
void HTS_Audio_flush(HTS_Audio * audio)
{
   /* No audio output on Windows */
   return;
}

/* HTS_Audio_close: close audio device */
void HTS_Audio_close(HTS_Audio * audio)
{
   if (audio->buff != NULL) {
      free(audio->buff);
      audio->buff = NULL;
   }
   audio->sampling_frequency = 0;
   audio->max_buff_size = 0;
   audio->buff_size = 0;
   audio->audio_interface = NULL;
}

/* HTS_Audio_clear: free audio */
void HTS_Audio_clear(HTS_Audio * audio)
{
   HTS_Audio_close(audio);
}