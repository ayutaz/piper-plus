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

/* Include necessary headers */
#include <stddef.h>  /* for NULL */
#include <stdlib.h>  /* for free */

/* Force AUDIO_PLAY_NONE for Windows builds */
#define AUDIO_PLAY_NONE

/* For Windows, we need to define the audio structure ourselves since */
/* HTS_hidden.h is an internal header that may not be available */

/* Define HTS_Audio structure for Windows */
typedef struct _HTS_Audio {
   int sampling_frequency;
   int max_buff_size;
   short *buff;
   int buff_size;
   void *audio_interface;
} HTS_Audio;

/* Define TRUE/FALSE if not already defined */
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

/* HTS Boolean type */
typedef int HTS_Boolean;

/* Forward declaration to avoid ordering issues */
void HTS_Audio_clear(HTS_Audio * audio);

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
      free(audio->buff);
   }
   HTS_Audio_initialize(audio);
}

HTS_AUDIO_C_END;

#endif                          /* !HTS_AUDIO_C */