/* -----------------------------------------------------------------------  */
/*           The HMM-Based Speech Synthesis System (HTS): version 1.1.1    */
/*                        HTS Working Group                                 */
/*                                                                          */
/* Copyright (c) 2001-2003 Nagoya Institute of Technology                  */
/*                         Department of Computer Science                   */
/*                                                                          */
/* Copyright (c) 2001-2008 Tokyo Institute of Technology                   */
/*                         Interdisciplinary Graduate School of             */
/*                         Science and Engineering                          */
/*                                                                          */
/* All rights reserved.                                                     */
/* -----------------------------------------------------------------------  */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Main headers */
#include "njd.h"
#include "jpcommon.h"
#include "text2mecab.h"
#include "mecab2njd.h"
#include "njd_set_pronunciation.h"
#include "njd_set_digit.h"
#include "njd_set_accent_phrase.h"
#include "njd_set_accent_type.h"
#include "njd_set_unvoiced_vowel.h"
#include "njd_set_long_vowel.h"
#include "njd2jpcommon.h"

#include "mecab.h"

#define MAXBUFLEN 1024

typedef struct _OpenJTalk {
   Mecab mecab;
   NJD njd;
   JPCommon jpcommon;
} OpenJTalk;

static void OpenJTalk_initialize(OpenJTalk * open_jtalk)
{
   Mecab_initialize(&open_jtalk->mecab);
   NJD_initialize(&open_jtalk->njd);
   JPCommon_initialize(&open_jtalk->jpcommon);
}

static void OpenJTalk_clear(OpenJTalk * open_jtalk)
{
   Mecab_clear(&open_jtalk->mecab);
   NJD_clear(&open_jtalk->njd);
   JPCommon_clear(&open_jtalk->jpcommon);
}

static int OpenJTalk_load(OpenJTalk * open_jtalk, const char *dn_mecab)
{
   if (Mecab_load(&open_jtalk->mecab, dn_mecab) != TRUE) {
      OpenJTalk_clear(open_jtalk);
      return 0;
   }
   return 1;
}

static int OpenJTalk_synthesis(OpenJTalk * open_jtalk, const char *txt, FILE * txtfp,
                        const char *outputfile)
{
   int result = 0;
   char buff[MAXBUFLEN];
   FILE *fp;

   text2mecab(buff, txt);
   Mecab_analysis(&open_jtalk->mecab, buff);
   mecab2njd(&open_jtalk->njd, Mecab_get_feature(&open_jtalk->mecab),
             Mecab_get_size(&open_jtalk->mecab));
   njd_set_pronunciation(&open_jtalk->njd);
   njd_set_digit(&open_jtalk->njd);
   njd_set_accent_phrase(&open_jtalk->njd);
   njd_set_accent_type(&open_jtalk->njd);
   njd_set_unvoiced_vowel(&open_jtalk->njd);
   njd_set_long_vowel(&open_jtalk->njd);
   njd2jpcommon(&open_jtalk->jpcommon, &open_jtalk->njd);
   JPCommon_make_label(&open_jtalk->jpcommon);

   /* output label file */
   if (outputfile != NULL) {
      fp = fopen(outputfile, "wt");
      if (fp != NULL) {
         int label_size = JPCommon_get_label_size(&open_jtalk->jpcommon);
         if (label_size > 2) {
            char **label_feature = JPCommon_get_label_feature(&open_jtalk->jpcommon);
            int i;
            for (i = 1; i < label_size - 1; i++) {
               fprintf(fp, "%s\n", label_feature[i]);
            }
         }
         fclose(fp);
      }
   }

   /* output label to stdout for parsing */
   if (txtfp != NULL) {
      int label_size = JPCommon_get_label_size(&open_jtalk->jpcommon);
      if (label_size > 2) {
         char **label_feature = JPCommon_get_label_feature(&open_jtalk->jpcommon);
         int i;
         for (i = 1; i < label_size - 1; i++) {
            fprintf(txtfp, "%s\n", label_feature[i]);
         }
      }
   }

   JPCommon_refresh(&open_jtalk->jpcommon);
   NJD_refresh(&open_jtalk->njd);
   Mecab_refresh(&open_jtalk->mecab);

   return result;
}

/* Usage: open_jtalk_phonemizer -x dic_dir [-ot label_file] [infile] */
int main(int argc, char **argv)
{
   int i;
   FILE *txtfp = stdin;
   char *txtfn = NULL;
   char *labfn = NULL;
   char *dn_mecab = NULL;
   char buff[MAXBUFLEN];

   OpenJTalk open_jtalk;

   /* parse command line */
   if (argc == 1) {
      fprintf(stderr,
              "The HMM-based speech synthesis system (HTS)\n");
      fprintf(stderr, "open_jtalk_phonemizer - Phoneme extraction tool\n");
      fprintf(stderr, "\n");
      fprintf(stderr, "usage: open_jtalk_phonemizer [ options ] [ infile ]\n");
      fprintf(stderr, "  options:                                                                   \n");
      fprintf(stderr, "    -x  dir        : dictionary directory                                  \n");
      fprintf(stderr, "    -ot file       : output trace/label file                              \n");
      fprintf(stderr, "    -h             : show this help message                               \n");
      fprintf(stderr, "  infile:\n");
      fprintf(stderr, "    text file                                                              \n");
      fprintf(stderr, "\n");
      return 1;
   }

   /* read command */
   for (i = 1; i < argc; i++) {
      if (argv[i][0] == '-') {
         if (strcmp(argv[i], "-x") == 0) {
            if (i + 1 < argc) {
               dn_mecab = argv[++i];
            }
         } else if (strcmp(argv[i], "-ot") == 0) {
            if (i + 1 < argc) {
               labfn = argv[++i];
            }
         } else if (strcmp(argv[i], "-h") == 0) {
            fprintf(stderr,
                    "usage: open_jtalk_phonemizer [ options ] [ infile ]\n");
            fprintf(stderr, "  options:                                                                   \n");
            fprintf(stderr, "    -x  dir        : dictionary directory                                  \n");
            fprintf(stderr, "    -ot file       : output trace/label file                              \n");
            fprintf(stderr, "    -h             : show this help message                               \n");
            fprintf(stderr, "  infile:\n");
            fprintf(stderr, "    text file                                                              \n");
            return 0;
         }
      } else {
         txtfn = argv[i];
      }
   }

   /* dictionary directory check */
   if (dn_mecab == NULL) {
      fprintf(stderr, "ERROR: open_jtalk_phonemizer: dictionary must be specified.\n");
      return 1;
   }

   /* open text file */
   if (txtfn != NULL) {
      txtfp = fopen(txtfn, "rt");
      if (txtfp == NULL) {
         fprintf(stderr, "ERROR: open_jtalk_phonemizer: cannot open text file %s.\n", txtfn);
         return 1;
      }
   }

   /* initialize */
   OpenJTalk_initialize(&open_jtalk);

   /* load dictionary */
   if (OpenJTalk_load(&open_jtalk, dn_mecab) != 1) {
      fprintf(stderr, "ERROR: open_jtalk_phonemizer: cannot load dictionary %s.\n", dn_mecab);
      if (txtfn != NULL)
         fclose(txtfp);
      return 1;
   }

   /* process text */
   if (txtfp != NULL) {
      while (fgets(buff, MAXBUFLEN - 1, txtfp) != NULL)
         OpenJTalk_synthesis(&open_jtalk, buff, stdout, labfn);
   }

   /* close file */
   if (txtfn != NULL)
      fclose(txtfp);

   /* clear memory */
   OpenJTalk_clear(&open_jtalk);

   return 0;
}