module github.com/ayutaz/piper-plus/src/go

go 1.26

require github.com/yalue/onnxruntime_go v1.27.0

require (
	github.com/ayutaz/piper-plus/src/go/phonemize v0.0.0
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/spf13/cobra v1.10.2
	github.com/spf13/pflag v1.0.9 // indirect
	golang.org/x/text v0.35.0 // indirect
)

replace github.com/ayutaz/piper-plus/src/go/phonemize => ./phonemize
