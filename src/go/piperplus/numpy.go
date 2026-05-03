package piperplus

// minimal numpy .npy reader.
//
// Supports version 1.0 / 2.0 with dtype '<f4' (little-endian float32) and
// 1-D (dim,) or 2-D (1, dim) shapes. Used by the CLI to load style vectors.

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"math"
	"os"
	"strings"
)

var npyMagic = []byte{0x93, 'N', 'U', 'M', 'P', 'Y'}

// LoadFloat32Npy reads a numpy .npy file and returns the contents as a
// []float32 (flattened). Accepts dtype '<f4' (little-endian float32) with
// 1-D (dim,) or 2-D (1, dim) shape. Returns an error for any other dtype,
// Fortran-order layout, or truncated header.
func LoadFloat32Npy(path string) ([]float32, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read npy: %w", err)
	}
	if len(data) < 10 || !bytes.HasPrefix(data, npyMagic) {
		return nil, fmt.Errorf("not a valid .npy file: %s", path)
	}
	major := data[6]
	var headerLen int
	var dataOffset int
	switch major {
	case 1:
		headerLen = int(binary.LittleEndian.Uint16(data[8:10]))
		dataOffset = 10 + headerLen
	case 2:
		headerLen = int(binary.LittleEndian.Uint32(data[8:12]))
		dataOffset = 12 + headerLen
	default:
		return nil, fmt.Errorf(".npy unsupported version: %d", major)
	}
	if len(data) < dataOffset {
		return nil, fmt.Errorf(".npy truncated header: %s", path)
	}
	headerStart := 10
	if major == 2 {
		headerStart = 12
	}
	header := string(data[headerStart : headerStart+headerLen])
	if !strings.Contains(header, "'descr': '<f4'") &&
		!strings.Contains(header, "\"descr\": \"<f4\"") {
		return nil, fmt.Errorf(
			".npy dtype must be '<f4' (little-endian float32); header: %s", header)
	}

	body := data[dataOffset:]
	if len(body)%4 != 0 {
		return nil, fmt.Errorf(
			".npy data size (%d bytes) not a multiple of 4", len(body))
	}
	count := len(body) / 4
	out := make([]float32, count)
	for i := 0; i < count; i++ {
		bits := binary.LittleEndian.Uint32(body[i*4 : i*4+4])
		out[i] = math.Float32frombits(bits)
	}
	return out, nil
}
