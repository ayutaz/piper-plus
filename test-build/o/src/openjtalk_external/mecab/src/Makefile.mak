
CC = cl
CL = link

CFLAGS = /O2 /Ob2 /Oi /Ot /Oy /GT /GL /TP /EHsc /D CHARSET_SHIFT_JIS /D DIC_VERSION=102 /D MECAB_WITHOUT_MUTEX_LOCK /D MECAB_DEFAULT_RC=\"dummy\" /D PACKAGE=\"open_jtalk\" /D VERSION=\"1.01\" /D HAVE_WINDOWS_H
LFLAGS = /LTCG

CORES = char_property.obj connector.obj context_id.obj dictionary.obj dictionary_compiler.obj dictionary_generator.obj dictionary_rewriter.obj eval.obj feature_index.obj iconv_utils.obj lbfgs.obj learner.obj learner_tagger.obj libmecab.obj mecab.obj nbest_generator.obj param.obj string_buffer.obj tagger.obj tokenizer.obj utils.obj viterbi.obj writer.obj

LIBS = mecab.lib Advapi32.lib

all: mecab.lib mecab-dict-index.exe

mecab.lib: $(CORES)
	lib $(LFLAGS) /OUT:$@ $(CORES)

mecab-dict-index.exe: mecab-dict-index.obj
	$(CL) /LTCG /OUT:$@ $(LIBS) $(@B).obj

.cpp.obj:
	$(CC) $(CFLAGS) /c $<

clean:
	del *.exe
	del *.lib
	del *.obj
