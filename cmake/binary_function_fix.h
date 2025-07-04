// Compatibility header for C++17 and later
// Provides std::binary_function which was deprecated in C++11 and removed in C++17

#ifndef BINARY_FUNCTION_FIX_H
#define BINARY_FUNCTION_FIX_H

#if __cplusplus >= 201703L
namespace std {
    template <typename Arg1, typename Arg2, typename Result>
    struct binary_function {
        typedef Arg1 first_argument_type;
        typedef Arg2 second_argument_type;
        typedef Result result_type;
    };
}
#endif

#endif // BINARY_FUNCTION_FIX_H