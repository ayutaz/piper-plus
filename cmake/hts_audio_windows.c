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

#ifndef HTS_AUDIO_C
#define HTS_AUDIO_C

#ifdef __cplusplus
#define HTS_AUDIO_C_START extern "C" {
#define HTS_AUDIO_C_END   }
#else
#define HTS_AUDIO_C_START
#define HTS_AUDIO_C_END
#endif                          /* __CPLUSPLUS */

HTS_AUDIO_C_START;

/* Force AUDIO_PLAY_NONE for Windows builds */
#define AUDIO_PLAY_NONE

/* hts_engine libraries */
#include "HTS_hidden.h"

/* HTS_Audio_initialize: initialize audio */
void HTS_Audio_initialize(HTS_Audio * audio)
{
   if (audio == NULL)
      return;
      
   audio->sampling_frequency = 0;
   audio->max_buff_size = 0;
   audio->buff = NULL;
   audio->buff_size = 0;
   audio->audio_interface = NULL;
}

/* HTS_Audio_set_parameter: set parameters for audio */
void HTS_Audio_set_parameter(HTS_Audio * audio, size_t sampling_frequency, size_t max_buff_size)
{
   if (audio == NULL)
      return;

   if (audio->sampling_frequency == sampling_frequency && audio->max_buff_size == max_buff_size)
      return;

   HTS_Audio_clear(audio);

   if (sampling_frequency == 0 || max_buff_size == 0)
      return;

   audio->sampling_frequency = sampling_frequency;
   audio->max_buff_size = max_buff_size;
   audio->buff = NULL;
   audio->buff_size = 0;
   audio->audio_interface = NULL;
}

/* HTS_Audio_write: send data to audio */
void HTS_Audio_write(HTS_Audio * audio, short data)
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

/* HTS_Audio_clear: free audio */
void HTS_Audio_clear(HTS_Audio * audio)
{
   if (audio == NULL)
      return;
      
   if (audio->buff != NULL) {
      HTS_free(audio->buff);
   }
   HTS_Audio_initialize(audio);
}

HTS_AUDIO_C_END;

#endif                          /* !HTS_AUDIO_C */